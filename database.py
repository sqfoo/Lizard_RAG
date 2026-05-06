import json, os
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate

from dotenv import load_dotenv
load_dotenv()

import time
TIME_TO_SLEEP = 10

from llm import HUGGINGFACE, GEMINI, setup_model

class Database:
    def __init__(self):
        self.embedding = self.setup_embedding()
        self.vector_store = InMemoryVectorStore(self.embedding)
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        self.docs = {}
        self.summary_llm = setup_model(HUGGINGFACE)
    
    def setup_embedding(self):
        embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en", model_kwargs={"device": "cpu"}, encode_kwargs={"normalize_embeddings": True}
        )
        return embeddings
    
    def add_file(self, file_path):
        """
        Add file to the docs

        Args:
            self: the Database instance, no need to pass when calling
            file_path: filepath of the PDF file
        
        Returns:
            bool: Succeed to add PDF file or not
        """
        try:
            if file_path not in self.docs.keys():
                loader = PyPDFLoader(file_path)
                docs = loader.load()
                
                all_splits = self.text_splitter.split_documents(docs)
                self.vector_store.add_documents(documents=all_splits)

                summary_prompt = ChatPromptTemplate.from_template(
                    "Extract the core technical themes and provide a 3-sentence summary of: {context}"
                )
                content_to_summarize = "\n".join([d.page_content for d in docs[:3]])
                summarized_chain = summary_prompt | self.summary_llm
                summary = summarized_chain.invoke({"context": content_to_summarize})
                self.docs[file_path] = summary.content
                time.sleep(TIME_TO_SLEEP)
            else:
                print(f'{file_path} already exists in the database')
            return True
        except:
            return False

    def retrieve(self, query: str):
        """
        Retrieve the query from the database

        Args:
            self: the Database instance, no need to pass when calling
            query: query string
        """
        retrieved_docs = self.vector_store.similarity_search(query, k=2)
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )
        time.sleep(TIME_TO_SLEEP)
        return serialized, retrieved_docs

    def save(self):
        self.vector_store.dump(path='dbs/database.json')
        with open('dbs/docs.json', 'w') as file:
            json.dump(self.docs, file, indent=4)
        print('Saved the database in database.json and docs.json')

    def load(self):
        if os.path.exists('dbs/database.json') and os.path.exists('dbs/docs.json'):
            # self.vector_store.load('dbs/database.json', self.embedding)
            with open('dbs/database.json', 'r') as file:
                self.vector_store.store = json.load(file)
            with open('dbs/docs.json', 'r') as file:
                self.docs = json.load(file)
            print('Loaded the database and docs before')
        else:
            print('There is no database and docs before')

database = Database()
database.load()