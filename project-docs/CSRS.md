**Task: Cybersecurity Standards RAG System**

**Objective:**  
> Develop an AI-powered Retrieval-Augmented Generation (RAG) application that enables users to ask questions about cybersecurity standards using locally hosted Large Language Models (LLMs). The application must ingest one or more cybersecurity documents and generate accurate, context-aware responses based solely on the uploaded content.

The application must run entirely offline after the required dependencies and models are installed.

**Task Requirements:**

**1\. Document Management**

> The application must:

* Accept PDF and TXT documents.  
* Automatically load every supported document from a designated docs/ directory.  
* Support multiple documents simultaneously.  
* Detect newly added documents without requiring code changes.  
* Provide a "Restart & Reload Documents" button to rebuild the knowledge base.

> Example supported standards include:

* NIST Cybersecurity Framework (CSF) 2.0  
* ISO 27001  
* NIST SP 800-53  
* CIS Controls  
* OWASP Documentation

> The system should be extensible so additional cybersecurity standards can be added simply by placing new documents into the docs/ folder.

**2\. Knowledge Base Construction**

> Implement a document ingestion pipeline that:

* Reads PDF and TXT files.  
* Extracts document text.  
* Splits documents into meaningful chunks.  
* Generates embeddings for every chunk.  
* Stores embeddings in a local vector store or in-memory index.

> The embedding process must occur automatically whenever documents are loaded or reloaded.

**3\. Semantic Retrieval**

> When a user asks a question, the application must:

* Generate an embedding for the user's query.  
* Retrieve the most relevant document chunks using semantic similarity.  
* Supply only the retrieved context to the language model.

> Keyword search alone is not sufficient.

**4\. Question Answering**

> The application should:

* Answer questions using retrieved document context.  
* Avoid generating information not present in the provided documents.  
* Inform the user when sufficient information cannot be found.  
* Preserve conversational context for follow-up questions (bonus if implemented).

> Example questions:

* What are the functions of the NIST Cybersecurity Framework?  
* Explain the Identify function.  
* What does ISO 27001 require for access control?  
* How is Incident Response handled?  
* What are the requirements for Asset Management?

**5\. User Interface**

> Develop the application using Streamlit.  
> The interface should include:

* Question input box  
* Generated answer  
* Loaded document list  
* Current model selection  
* Restart & Reload Documents button  
* Sidebar containing application settings

**6\. Local LLM Integration**  
> The application must use Ollama for local model inference.  
> Cloud-based APIs such as OpenAI, Gemini, Claude, Cohere, etc., are not permitted.  
>   
> Required Models:  
> >   
> > Embedding Model (Mandatory)

* nomic-embed-text  
  This model must always be used for embedding generation.  
    
  Supported LLMs (Mandatory):  
* llama3.2  
* qwen2.5:1.5b  
* gemma2:2b  
* phi4-mini  
* gemma4:e2b  
  Users should be able to select the desired model from a dropdown in the UI.

**Your solution must:**

* Load multiple PDF/TXT files  
* Build embeddings automatically  
* Perform semantic retrieval  
* Generate responses using retrieved context  
* Allow LLM selection  
* Support document reload  
* Display loaded documents  
* Run completely offline  
* Be modular and maintainable

**Submit the following:**

* Complete source code  
* README.md containing:  
* Installation instructions  
* Setup instructions  
* How to add new documents  
* How to run the application  
* requirements.txt or pyproject.toml  
* Sample cybersecurity document(s) used for testing

