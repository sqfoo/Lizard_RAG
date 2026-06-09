import os
import re
import requests
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

@tool
def duckduck_websearch(query: str) -> str:
    """
    Performs a web search using the given query, downloads the content of two relevant web pages,
    and returns their combined content as a raw string.

    This is useful when the task requires analysis of web page content, such as retrieving poems, 
    changelogs, or other textual resources.

    Args:
        query (str): The search query.

    Returns:
        str: The combined raw text content of the two retrieved web pages.
    """
    search_engine = DuckDuckGoSearchResults(output_format="list", num_results=2)
    page_urls = [url["link"] for url in search_engine(query)]

    loader = WebBaseLoader(web_paths=(page_urls))
    docs = loader.load()

    combined_text = "\n\n".join(doc.page_content[:15000] for doc in docs)

    # Clean up excessive newlines, spaces and strip leading/trailing whitespace
    cleaned_text = re.sub(r'\n{3,}', '\n\n', combined_text).strip()
    cleaned_text = re.sub(r'[ \t]{6,}', ' ', cleaned_text)

    # Strip leading/trailing whitespace
    cleaned_text = cleaned_text.strip()
    return cleaned_text

@tool
def serper_websearch(query: str) -> str:
    """
    Performs a web search using the given query with SERPER Search Engine

    Args:
        query (str): The search query.
    
    Returns:
        str: the search result
    """
    search = GoogleSerperAPIWrapper(serper_api_key=os.getenv("SERPER_API_KEY"))
    results = search.run(query)
    return results

@tool
def visit_webpage(url: str) -> str:
    """
    Fetches raw HTML content of a web page.
    
    Args:
        url: the webpage url
    
    Returns:
        str: The combined raw text content of the webpage
    """
    try:
        response = requests.get(url, timeout=5)
        return response.text[:5000]
    except Exception as e:
        return f"[ERROR fetching {url}]: {str(e)}"

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
    docs = retriever.invoke(query)
    combined_text = "\n\n".join(doc.page_content for doc in docs)
    return combined_text

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