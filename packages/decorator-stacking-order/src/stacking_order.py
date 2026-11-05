import functools


def make_logged(name):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            print(f"[{name}] enter")
            result = func(*args, **kwargs)
            print(f"[{name}] exit")
            return result
        return wrapper
    return decorator


@make_logged("outer")
@make_logged("inner")
def work():
    print("[work] body")
    return 1


if __name__ == "__main__":
    print("호출 시작")
    work()
    print("호출 끝")
