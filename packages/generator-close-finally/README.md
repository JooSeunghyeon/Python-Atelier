# 제너레이터 close()와 finally 블록

제너레이터를 close()로 명시 종료할 때 finally 블록이 실행되는지, GeneratorExit를 잡으면 어떻게 되는지 여러 상황별로 확인한다.

실행 방법: `python src/generator_close_finally.py`

테스트하는 상황:
- 시작된 제너레이터를 close()하면 finally 실행
- 이미 소진된 제너레이터를 close()해도 finally 재실행 안 됨
- GeneratorExit를 잡고 return하면 정상 종료
- GeneratorExit를 잡고 yield하면 RuntimeError
- close() 뒤 next() 호출은 StopIteration
- 시작되지 않은 제너레이터를 close()하면 finally 실행 안 됨
