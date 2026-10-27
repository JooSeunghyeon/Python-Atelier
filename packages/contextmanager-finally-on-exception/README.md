# contextmanager의 finally 해제 확인

이 폴더는 contextlib.contextmanager 데코레이터와 try/finally 구문을 함께 사용하는 경우를 다룬다. yield 앞에서 리소스를 획득하고 yield 뒤 finally에서 해제하는 구조다.

본문에서 정상 종료하는 경우와 예외를 던지는 경우를 각각 실행해 finally 블록이 두 경우 모두 실행되는지 확인한다. 예외는 with 블록을 빠져나가 바깥으로 전파된다.

실행은 python src/contextmanager_finally.py 로 한다. 출력에서 획득, 해제 메시지의 순서를 본다.
