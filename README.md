# Python Atelier

실행해 본 코드를 폴더로 나눠 두었다. 다시 볼 때는 그 폴더 README를 먼저 연다.

## 목록

- [small-example](packages/small-example/README.md): Python 함수 정의와 리스트 순회를 보여주는 짧은 예제
- [generator-skip-blank-lines](packages/generator-skip-blank-lines/README.md): 제너레이터 표현식으로 파일 줄을 지연 평가하면서 빈 줄과 주석 줄을 건너뛰는 흐름을 확인한다.
- [contextmanager-finally-on-exception](packages/contextmanager-finally-on-exception/README.md): contextlib.contextmanager에서 yield 앞뒤로 리소스를 획득하고 해제하며, 본문에서 예외가 나도 finally 구간이 실행되는지 확인한다.
- [stable-sort-key-order](packages/stable-sort-key-order/README.md): sorted()와 list.sort()에서 key 함수가 같은 값을 돌려줄 때 원래 삽입 순서가 유지되는지 여러 key 함수로 확인한다.
