from pydantic import BaseModel


class PublishResultsRequest(BaseModel):
    show_model_answer: bool = False
    show_answer_sheet: bool = True
    show_question_paper: bool = True
