### Evaluation of the assistant


#### Dummy test (my intuition)
For each embedded question I would use an llm to rephrase it and expect the original answser back from the RAG.
Base on that I would compute persantage % (how many questions did it return right)

----

#### Use LLM-as-a-judge (after doing some research)

Use and llm to compute the results of another llm

- Create a list of (questions, expected answer)
- Run the rag.ask(questions)
- And compute these mestrics
  - Correctness - expected answer vs given answer
  - Retrieval relevance - question vs retrieved docs
  - Groundedness - retrieved docs vs given answer
  - Answer relevance - given answer vs question