import boa

if __name__ == "__main__":
    boa.env.fork(url="http://localhost:8545")
    test = boa.load("test.vy")
    print(test.test2())
