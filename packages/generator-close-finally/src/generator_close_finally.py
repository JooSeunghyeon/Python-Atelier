"""제너레이터 close() 메서드와 finally 블록의 동작을 확인한다."""


def started_close_calls_finally():
    """시작된 제너레이터를 close()하면 finally 블록이 실행된다."""
    print("\n=== 시작된 제너레이터 close() → finally 실행 ===")
    
    def generator_with_finally():
        try:
            print("제너레이터 시작")
            yield 1
            yield 2
        finally:
            print("finally 블록 실행됨")
    
    gen = generator_with_finally()
    value = next(gen)
    print(f"첫 값: {value}")
    gen.close()
    print("close() 완료")


def exhausted_close_no_finally():
    """이미 소진된 제너레이터를 close()해도 finally는 재실행되지 않는다."""
    print("\n=== 소진된 제너레이터 close() → finally 재실행 안 됨 ===")
    
    def generator_with_finally():
        try:
            print("제너레이터 시작")
            yield 1
        finally:
            print("finally 블록 실행됨 (소진 시)")
    
    gen = generator_with_finally()
    value = next(gen)
    print(f"값: {value}")
    
    try:
        next(gen)
    except StopIteration:
        print("StopIteration 발생 (제너레이터 소진)")
    
    gen.close()
    print("close() 완료 (finally 재실행 안 됨)")


def generator_exit_caught_return():
    """GeneratorExit를 잡고 return하면 정상 종료된다."""
    print("\n=== GeneratorExit 잡고 return → 정상 종료 ===")
    
    def generator_catching_exit():
        try:
            print("제너레이터 시작")
            yield 1
            yield 2
        except GeneratorExit:
            print("GeneratorExit 감지, return으로 종료")
            return
    
    gen = generator_catching_exit()
    value = next(gen)
    print(f"첫 값: {value}")
    gen.close()
    print("close() 완료 (정상 종료)")


def generator_exit_caught_yield_raises():
    """GeneratorExit를 잡고 yield하면 RuntimeError가 발생한다."""
    print("\n=== GeneratorExit 잡고 yield → RuntimeError ===")
    
    def generator_yielding_on_exit():
        try:
            print("제너레이터 시작")
            yield 1
            yield 2
        except GeneratorExit:
            print("GeneratorExit 감지, yield 시도")
            yield 99  # 이 시도는 RuntimeError를 일으킨다
    
    gen = generator_yielding_on_exit()
    value = next(gen)
    print(f"첫 값: {value}")
    
    try:
        gen.close()
    except RuntimeError as e:
        print(f"RuntimeError 발생: {e}")


def close_then_next_raises_stopiteration():
    """close() 후 next()를 호출하면 StopIteration이 발생한다."""
    print("\n=== close() 후 next() → StopIteration ===")
    
    def simple_generator():
        yield 1
        yield 2
    
    gen = simple_generator()
    value = next(gen)
    print(f"첫 값: {value}")
    gen.close()
    print("close() 완료")
    
    try:
        next(gen)
    except StopIteration:
        print("next() 호출 시 StopIteration 발생")


def unstarted_close_no_finally():
    """시작되지 않은 제너레이터를 close()하면 finally가 실행되지 않는다."""
    print("\n=== 시작 안 된 제너레이터 close() → finally 실행 안 됨 ===")
    
    def generator_with_finally():
        try:
            print("제너레이터 시작 (이 메시지는 출력 안 됨)")
            yield 1
        finally:
            print("finally 블록 (이 메시지도 출력 안 됨)")
    
    gen = generator_with_finally()
    print("제너레이터 생성만 함 (next() 호출 안 함)")
    gen.close()
    print("close() 완료 (finally 실행 안 됨)")


if __name__ == "__main__":
    started_close_calls_finally()
    exhausted_close_no_finally()
    generator_exit_caught_return()
    generator_exit_caught_yield_raises()
    close_then_next_raises_stopiteration()
    unstarted_close_no_finally()
    
    print("\n모든 테스트 완료")
