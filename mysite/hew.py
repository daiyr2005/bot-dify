import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import ChatOllama
from langchain_text_splitters import RecursiveCharacterTextSplitter


loaders = TextLoader('nnn.txt', encoding='utf-8')
document = loaders.load()

text_spliter = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=20
)

chunks = text_spliter.split_documents(document)

embeddings = OllamaEmbeddings(
    model="nomic-embed-text",
)

vector_store = InMemoryVectorStore.from_documents(chunks, embeddings)

prompt = ChatPromptTemplate(
    [
        (
            'system',
            'Ты онлайн менеджер академии Motion Web. '
            'При ответе ты должен сначала посмотреть Базу Знаний: '
            '"База знаний {base_knowledge}" '
            'Должен отвечать на вопросы коротко и вежливо. '
            '"Если не нашел ответ в базе знаний напиши что не знаешь. "'
        ),
        (
            'human',
            '{content}'
        )
    ]
)

model = ChatOllama(
    model='llama3.2:latest',
    temperature=0
)

chain = prompt | model | StrOutputParser()

test_app = FastAPI()


class QuestionSchema(BaseModel):
    question: str


@test_app.post('/questions/')
async def answer(data: QuestionSchema):
    data = data.question.strip()

    if not data:
        raise HTTPException(status_code=400, detail='Маалымат берилген жок')

    new_document = vector_store.similarity_search(data, k=1)

    final_answer = chain.invoke({'content': data, 'base_knowledge': new_document})
    return {'answer': final_answer}


if __name__ == '__main__':
    uvicorn.run(test_app, host='127.0.0.1', port=8000)