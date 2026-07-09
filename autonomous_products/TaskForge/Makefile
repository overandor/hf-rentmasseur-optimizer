.PHONY: run test clean demo

run:
	python3 main.py status

test:
	python3 -m pytest test_cli.py -v

demo:
	python3 main.py add "Build the product" -p 3
	python3 main.py add "Write tests" -p 2
	python3 main.py add "Ship to App Store" -p 5
	python3 main.py list
	python3 main.py done 1
	python3 main.py list
	python3 main.py receipts
	python3 main.py status

clean:
	rm -rf __pycache__ *.db
