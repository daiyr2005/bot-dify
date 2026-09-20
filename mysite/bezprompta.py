from fastapi import FastAPI, HTTPException
import uvicorn
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

test_app = FastAPI()

loader = TextLoader("nnn.txt", encoding='utf-8')
document = loader.load()

context_text = document[0].page_content

docs = Document(
    page_content='Motion web курсы и дфнные',
    metadata={"source": f'{document}'}
)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=100,
    chunk_overlap=10,
    length_function=len
)

chunks = text_splitter.split_text(str(document))

# Промпт оставлен БЕЗ изменений
promp = ChatPromptTemplate(
    [
        (
            'system',
            'Ты онлайн ассистент и должен отвечать на вапросы вежливо. '
        ),
        (
            'human',  # Исправлено: humen -> human
            "{text}"
        )
    ]
)

model = ChatOllama(
    model='llama3.2:latest',
    temperature=0
)

chain = promp | model | StrOutputParser()


class QuestionShema(BaseModel):
    question: str

@test_app.post('/questions/')
async def answer_for_question(text: QuestionShema):
    question = text.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail='Маалымат жок экен')

    # Проверка: есть ли слова из вопроса в nnn.txt (без изменения промпта)
    words = [word.lower() for word in question.split() if len(word) > 2]
    has_match = any(word in context_text.lower() for word in words)

    if not has_match:
        return {"answer": "Я не знаю."}

    # Если совпадение есть — отправляем в модель
    response = chain.invoke({'text': question})
    return {"answer": response}


if __name__ == '__main__':
    uvicorn.run(test_app, host='127.0.0.1', port=8000)