import logging
import configparser
import pdfplumber
import os
from pptx import Presentation
from sentence_transformers import SentenceTransformer
import chromadb
import requests
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

# === Logging Setup ===
logging.basicConfig(
    level=logging.INFO,
    filename='logs/script.log',
    filemode='w',
    encoding='utf-8',
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.info("Logging initialized")

# === Config Setup ===
config = configparser.ConfigParser()
config.read('logs/configfile.properties')
logging.info("Config loaded")

# === Constants ===
MODEL_NAME = "all-MiniLM-L6-v2"
OLLAMA_MODEL = "tinyllama"
CHROMA_DIR = "TechTriad"

# === Helper: Check if word is within a table bounding box ===
def is_within_bbox(word, bbox):
    x0, y0, x1, y1 = bbox
    wx0, wy0, wx1, wy1 = float(word['x0']), float(word['top']), float(word['x1']), float(word['bottom'])
    return wx0 >= x0 and wx1 <= x1 and wy0 >= y0 and wy1 <= y1

# === Function: Extract text from PDFs (excluding tables) ===
def extract_text_from_pdfs(config):
    pdf_dir = config.get("path", "pdf_dir")
    output_folder = "outputs"
    os.makedirs(output_folder, exist_ok=True)

    for file_name in os.listdir(pdf_dir):
        if file_name.endswith('.pdf'):
            pdf_path = os.path.join(pdf_dir, file_name)
            with pdfplumber.open(pdf_path) as doc:
                for i, page in enumerate(doc.pages, start=1):
                    words = page.extract_words()
                    tables = page.find_tables()
                    table_bboxes = [table.bbox for table in tables]
                    non_table_words = [word['text'] for word in words if not any(is_within_bbox(word, bbox) for bbox in table_bboxes)]

                    clean_text = ' '.join(non_table_words)
                    base_name = os.path.splitext(file_name)[0]
                    text_file_path = os.path.join(output_folder, f"{base_name}_page_{i}.txt")

                    with open(text_file_path, 'w', encoding='utf-8') as text_file:
                        text_file.write(clean_text + "\n\n")
                        for table in tables:
                            for row in table.extract():
                                text_file.write("\t".join(cell or '' for cell in row) + "\n")
                            text_file.write("\n")

# === Chunking ===
def chunk_text(text, chunk_size=500, overlap=100):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks

def chunk_all_texts():
    output_folder = "outputs"
    all_chunks = []
    for file_name in os.listdir(output_folder):
        if file_name.endswith('.txt'):
            with open(os.path.join(output_folder, file_name), 'r', encoding='utf-8') as f:
                text = f.read()
                chunks = chunk_text(text)
                all_chunks.extend([chunk for chunk in chunks if chunk.strip()])
    logging.info(f" Total chunks created: {len(all_chunks)}")
    if all_chunks:
        logging.info(f" Sample chunk: {all_chunks[0][:200]}")
    return all_chunks

# === Build Vector DB (and persist) ===
def build_vector_db(chunks):
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = chroma_client.get_or_create_collection(name="company-capabilities")

    model = SentenceTransformer(MODEL_NAME)

    if collection.count() == 0:
        logging.info(" Storing new chunks into vector DB...")
        documents = []
        embeddings = []
        ids = []
        for idx, chunk in enumerate(chunks):
            if chunk.strip():
                embedding = model.encode(chunk).tolist()
                documents.append(chunk)
                embeddings.append(embedding)
                ids.append(f"chunk_{idx}")
        collection.add(documents=documents, embeddings=embeddings, ids=ids)
        logging.info(f" Stored {len(documents)} documents in ChromaDB.")
    else:
        logging.info(" Vector DB already populated.")

    return collection, model

# === Query Bot ===
def query_bot(question, collection, model):
    question_embedding = model.encode(question).tolist()
    results = collection.query(query_embeddings=[question_embedding], n_results=5)

    retrieved_docs = results.get('documents', [[]])[0]
    logging.info(f" Retrieved Documents: {retrieved_docs}")

    if not retrieved_docs or all(not doc.strip() for doc in retrieved_docs):
        return " Sorry, I couldn't find relevant context to answer that."

    context = "\n\n".join(retrieved_docs)
    prompt = f"""
You are an intelligent assistant. Use the provided context to answer the user's question accurately and concisely.

Context:
{context}

Question:
{question}

Answer:
"""
    logging.info(f" Prompt Sent to Ollama:\n{prompt}")

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    )

    if response.status_code == 200:
        return response.json().get('response', " No response received from model.")
    else:
        return f" Error from Ollama: {response.text}"

# === CLI Mode: Ask question from terminal ===
def ask_from_cli():
    try:
        logging.info(" Ready to answer CLI questions.")
        while True:
            question = input("\n💬 Your question (or type 'exit'): ")
            if question.lower() == 'exit':
                print(" Exiting.")
                break
            if question.strip():
                response = query_bot(question, collection, model)
                print("\n Bot's Response:\n", response)
            else:
                print("⚠️ Please enter a valid question.")
    except Exception as e:
        logging.exception(" Error during CLI question-answering.")

# === Data Preprocessing ===
def main():
    try:
        extract_text_from_pdfs(config)
        all_chunks = chunk_all_texts()
        build_vector_db(all_chunks)
        logging.info(" All files processed and stored in vector DB.")
    except Exception as e:
        logging.exception(" Error occurred during processing")

# === Flask App Setup ===
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# === Preload Chunks & Model Only Once ===
extract_text_from_pdfs(config)
chunks = chunk_all_texts()
collection, model = build_vector_db(chunks)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask():
    data = request.get_json()
    question = data.get('question', '')

    if question.strip():
        answer = query_bot(question, collection, model)
        return jsonify({"response": answer})
    return jsonify({"response": " Please enter a question."})

# === Entry Point ===
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'cli':
        ask_from_cli()
    else:
        app.run(debug=True, use_reloader=False)
