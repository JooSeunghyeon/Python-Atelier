from contextlib import contextmanager


class FakeResource:
    def __init__(self, name):
        self.name = name
        self.closed = False

    def read(self):
        if self.closed:
            raise RuntimeError(f"{self.name} is already closed")
        return f"data from {self.name}"

    def close(self):
        self.closed = True


@contextmanager
def open_resource(name):
    resource = FakeResource(name)
    print(f"[acquire] {name}")
    try:
        yield resource
    finally:
        resource.close()
        print(f"[release] {name} closed={resource.closed}")


def run_normal():
    with open_resource("normal") as res:
        print(res.read())
    print("after normal block")


def run_with_error():
    try:
        with open_resource("error") as res:
            print(res.read())
            raise ValueError("body failed")
    except ValueError as exc:
        print(f"caught outside: {exc}")


if __name__ == "__main__":
    run_normal()
    print("---")
    run_with_error()
