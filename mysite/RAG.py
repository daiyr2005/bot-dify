from fastapi import FastAPI, HTTPException
import uvicorn
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import TextLoader

test_app = FastAPI()

loader = TextLoader("nnn.txt", encoding='utf-8')
document = loader.load()

context_text = document[0].page_content

promp = ChatPromptTemplate(
    [
        (
            'system',
            'Ты онлайн ассистент и должен отвечать на вопросы вежливо.\n'
            'Используй ТОЛЬКО следующий контекст для ответа на вопрос:\n'
            '{context}\n\n'  
            'Если ответа на вопрос нет в контексте, ответь строго: "Я не знаю."'
        ),
        (
            'human',
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

    response = chain.invoke({
        'context': context_text,
        'text': question
    })
    return {"answer": response}


if __name__ == '__main__':
    uvicorn.run(test_app, host='127.0.0.1', port=8000)