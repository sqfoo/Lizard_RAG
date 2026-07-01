import os
import re
import time
import requests
import random
import pandas as pd
from typing import List
from dotenv import load_dotenv

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