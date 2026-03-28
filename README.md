# 📊 Financial Document Management System with RAG

## 🚀 Overview

This project is an AI-powered financial document management system built using FastAPI. It allows users to upload, manage, and semantically search financial documents using Retrieval-Augmented Generation (RAG).

## 🛠️ Tech Stack

* FastAPI
* PostgreSQL
* SQLAlchemy
* JWT Authentication
* FAISS (Vector DB)
* Sentence Transformers

## 🔐 Features

* User Authentication (JWT)
* Role-Based Access Control (RBAC)
* Document Upload & Management
* Semantic Search using AI
* Financial insights retrieval

## 📂 Project Structure

app/

* api/
* models/
* schemas/
* services/
* utils/

## ⚙️ Setup Instructions

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/financial-doc-rag-fastapi.git
cd financial-doc-rag-fastapi
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Server

```bash
uvicorn app.main:app --reload
```

## 📬 API Endpoints

* /auth/register
* /auth/login
* /documents/upload
* /rag/search

## 🎯 Future Enhancements

* Docker support
* Frontend UI
* Advanced reranking model

## 👨‍💻 Author

Tushar Sanap
