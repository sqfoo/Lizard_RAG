import os
import re
import ta
import time
import json
import requests
import random
import pandas as pd
from pandas import DataFrame
from typing import List
from dotenv import load_dotenv
import yfinance as yf
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from langchain_core.tools import tool
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.retrievers import WikipediaRetriever
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_community.document_loaders import ImageCaptionLoader

from core.database import database
load_dotenv()

MAX_RETRIES = 5
BASE_TIME = 10

def with_retries(fn, *, name: str):
    error = None

    for i in range(1, MAX_RETRIES + 1):
        try:
            return fn()

        except Exception as e:
            error = str(e)

            sleep_time = BASE_TIME * (2 ** (i - 1)) + random.uniform(0, 1.5)

            print(f"[{name}] attempt {i}/{MAX_RETRIES} failed: {error}")
            print(f"[{name}] retrying in {sleep_time:.1f}s")

            time.sleep(sleep_time)

    return f"[{name}] failed after {MAX_RETRIES} attempts: {error or 'unknown error'}"

@tool
def duckduck_websearch(query: str) -> str:
    """
    Performs a web search using DuckDuckGo, fetches up to 2 pages,
    and returns cleaned text content.
    
    Args:
        query (str): The search query.
    
    Returns:
        str: the search result
    """

    def run():
        search_engine = DuckDuckGoSearchResults(
            output_format="list",
            num_results=2
        )

        results = search_engine.invoke(query)

        if not results:
            raise RuntimeError("Empty search results")

        urls = list({r.get("link") for r in results if r.get("link")})

        if not urls:
            return f"No URLs found for '{query}'"

        docs = WebBaseLoader(web_paths=tuple(urls)).load()

        text = "\n\n".join((d.page_content or "")[:15000] for d in docs)

        if not text.strip():
            return "No readable content extracted"

        text = text.replace("\r\n", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)

        return text.strip()

    return with_retries(run, name="duckduck_websearch")

@tool
def serper_websearch(query: str) -> str:
    """
    Performs a web search using the given query with SERPER Search Engine

    Args:
        query (str): The search query.
    
    Returns:
        str: the search result
    """

    def run():
        search = GoogleSerperAPIWrapper(
            serper_api_key=os.getenv("SERPER_API_KEY")
        )
        return search.run(query)

    return with_retries(run, name="serper_websearch")

@tool
def visit_webpage(url: str) -> str:
    """
    Fetches raw HTML content of a web page.
    
    Args:
        url: the webpage url
    
    Returns:
        str: The combined raw text content of the webpage
    """

    def run():
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")

        return response.text[:5000]

    return with_retries(run, name="visit_webpage")

@tool
def wiki_search(query: str) -> str:
    """
    Searches for a Wikipedia articles using the provided query and returns the content of the corresponding Wikipedia pages.

    Args:
        query (str): The search term to look up on Wikipedia.

    Returns:
        str: The text content of the Wikipedia articles related to the query.
    """
    retriever = WikipediaRetriever()

    def run():
        docs = retriever.invoke(query)
        return "\n\n".join(doc.page_content for doc in docs)

    return with_retries(run, name="wiki_search")

@tool
def youtube_viewer(youtube_url: str, question: str) -> str:
    """
    Analyzes a YouTube video from the provided URL and returns an answer 
    to the given question based on the analysis results.

    Args:
        youtube_url (str): The URL of the YouTube video, in the format 
            "https://www.youtube.com/...".
        question (str): A question related to the content of the video.

    Returns:
        str: An answer to the question based on the video's content.
    """

    error = ""
    for i in range(1, 1+MAX_RETRIES):
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model='models/gemini-2.5-flash-preview-04-17',
                contents=types.Content(
                    parts=[
                        types.Part(
                            file_data=types.FileData(file_uri=youtube_url)
                        ),
                        types.Part(text=question)
                    ]
                )
            )
            return response.text
        
        except Exception as e:
            error = str(e)
            sleep_time = BASE_TIME*2**i
            print(f"An error occurred while executing the web search: {error}, and retrying in {sleep_time} seconds")
            time.sleep(sleep_time)
            continue
    
    return f"An error occurred while viewing the youtube_url: {youtube_url}: {error}"
    
@tool
def image_caption(dir: str) -> str:
    """
    Understand the content of the provided image
    
    Args:
        dir: the image url link
    
    Returns:
        str: the image caption
    """
    loader = ImageCaptionLoader(images=[dir])
    metadata = loader.load()
    return metadata[0].page_content

@tool
def run_python(code: str):
    """ Run the given python code
    
    Args:
        code: the python code
    """
    return exec(code)

@tool
def multiply(a: float, b: float) -> float:
    """
    Multiply two numbers.
    
    Args:
        a: first float
        b: second float
    
    Returns:
        float: the multiplication of a and b
    """
    return a * b

@tool
def add(a: float, b: float) -> float:
    """
    Add two numbers.
    
    Args:
        a: first float
        b: second float
    
    Returns:
        float: the sum of a and b
    """
    return a + b

@tool
def subtract(a: float, b: float) -> float:
    """
    Subtract two numbers.
    
    Args:
        a: first float
        b: second float
    
    Returns:
        float: the result after a subtracted by b
    """
    return a - b

@tool
def divide(a: float, b: float) -> float:
    """Divide two numbers.
    
    Args:
        a: first float
        b: second float
    
    Returns:
        float: the result after a divided by b
    """
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b

@tool
def upload_new_source(path: str) -> bool:
    """
    Add file to the database

    Args:
        path: filepath of the PDF file
    
    Returns:
        bool: Succeed to add PDF file or not
    """
    return database.add_file(path)
    
@tool(response_format="content_and_artifact")
def fetch_existing_data(query: str) -> str:
    """
        Retrieve the query from the database

    Args:
        query: query string
    
    Returns:
        str: Retrieved Content
    """
    serialized, retrieved_docs = database.retrieve(query)
    return serialized, retrieved_docs

from typing import Dict, List

import pandas as pd
import ta
import yfinance as yf
from langchain_core.tools import tool


# ============================================================================
# Internal Helpers
# ============================================================================

def _get_history(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:
    """Download historical OHLCV data."""

    return yf.Ticker(symbol).history(
        period=period,
        interval=interval,
    )


def _compute_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute common technical indicators."""

    df = df.copy()

    df["SMA20"] = ta.trend.sma_indicator(df["Close"], window=20)
    df["EMA20"] = ta.trend.ema_indicator(df["Close"], window=20)

    df["RSI"] = ta.momentum.rsi(df["Close"])

    df["MACD"] = ta.trend.macd(df["Close"])

    df["ADX"] = ta.trend.adx(
        df["High"],
        df["Low"],
        df["Close"],
    )

    return df


def _df_to_records(df: pd.DataFrame) -> List[Dict]:
    """Convert DataFrame into JSON serializable records."""

    if df.empty:
        return []

    df = df.copy()

    if isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()

    return df.where(pd.notnull(df), None).to_dict(orient="records")


# ============================================================================
# Tools
# ============================================================================

@tool
def get_historical_prices(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> List[Dict]:
    """
    Download historical OHLCV data.

    Returns:
        List of daily (or interval) price records.
    """

    df = _get_history(symbol, period, interval)

    return _df_to_records(df)


@tool
def get_company_fundamentals(symbol: str) -> Dict:
    """
    Retrieve the company's fundamental metrics.
    """

    info = yf.Ticker(symbol).info

    keys = [
        "longName",
        "sector",
        "industry",
        "marketCap",
        "trailingPE",
        "forwardPE",
        "priceToBook",
        "beta",
        "dividendYield",
        "returnOnEquity",
        "profitMargins",
        "currentRatio",
        "debtToEquity",
        "earningsGrowth",
        "revenueGrowth",
    ]

    return {
        key: info.get(key)
        for key in keys
    }


@tool
def get_financial_statements(symbol: str) -> Dict:
    """
    Retrieve the latest financial statements.
    """

    ticker = yf.Ticker(symbol)

    return {
        "income_statement": _df_to_records(
            ticker.financials
        ),
        "balance_sheet": _df_to_records(
            ticker.balance_sheet
        ),
        "cash_flow": _df_to_records(
            ticker.cashflow
        ),
    }


@tool
def get_dividend_history(symbol: str) -> List[Dict]:
    """
    Retrieve dividend payment history.
    """

    dividends = yf.Ticker(symbol).dividends.to_frame(
        name="Dividend"
    )

    return _df_to_records(dividends)


@tool
def get_market_indices() -> Dict:
    """
    Retrieve recent market index performance.
    """

    symbols = {
        "S&P500": "^GSPC",
        "NASDAQ": "^IXIC",
        "DOW": "^DJI",
        "RUSSELL2000": "^RUT",
        "VIX": "^VIX",
    }

    result = {}

    for name, ticker in symbols.items():

        history = yf.Ticker(ticker).history(period="5d")

        result[name] = _df_to_records(history)

    return result


@tool
def run_technical_analysis(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> Dict:
    """
    Compute technical indicators for the specified stock.

    Returns only the latest indicator values together with
    recent price history.
    """

    df = _get_history(
        symbol=symbol,
        period=period,
        interval=interval,
    )

    if df.empty:
        return {
            "symbol": symbol,
            "error": "No historical data available.",
        }

    df = _compute_technical_indicators(df)

    latest = df.iloc[-1]

    return {
        "symbol": symbol.upper(),

        "latest_price": float(latest["Close"]),

        "technical_indicators": {
            "SMA20": float(latest["SMA20"]) if pd.notna(latest["SMA20"]) else None,
            "EMA20": float(latest["EMA20"]) if pd.notna(latest["EMA20"]) else None,
            "RSI": float(latest["RSI"]) if pd.notna(latest["RSI"]) else None,
            "MACD": float(latest["MACD"]) if pd.notna(latest["MACD"]) else None,
            "ADX": float(latest["ADX"]) if pd.notna(latest["ADX"]) else None,
        },

        "recent_prices": _df_to_records(df.tail(30)),
    }

@tool
def stock_news(stock: str) -> str:
    """
    Fetch the news related to that stock

    Args:
        stock: str

    Returns:
        str: news related to stock
    
    """
    return duckduck_websearch(f'Today {stock}')

@tool
def fetch_news() -> str:
    """
    Fetch the current news

    Args:

    Returns:
        str: news related to stock
    
    """
    return duckduck_websearch(f'Today News')