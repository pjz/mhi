
PROJ=mhi

PIP=./env/bin/pip
PYTEST=./env/bin/py.test
PYTEST_ARGS=-v --timeout=60
PYTHON=python

env:
	virtualenv --python=python2.7 env
	$(PIP) install -e .

test: env
	if [ ! -f $(PYTEST) ]; then \
		$(PIP) install pytest ;\
		$(PIP) install pytest-runfailed ;\
		$(PIP) install pytest-timeout ;\
	fi
	cd tests && ../$(PYTEST) $(PYTEST_ARGS)

testf: env
	cd tests && ../$(PYTEST) --failed $(PYTEST_ARGS)

testf-clean: env clean-testf
	cd tests && ../$(PYTEST) --failed $(PYTEST_ARGS)

clean-testf:
	rm -rf tests/.pytest

clean: clean-testf
	rm -rf env build dist
	find . -name __pycache__ | xargs rm -rf
	find . -name \*.pyc | xargs rm -f

wheel:
	$(PYTHON) setup.py bdist_wheel

release:
	@if git tag | grep -q $(PROJ)-`$(PYTHON) setup.py -V` ; then\
		echo "Already released this version.";\
		echo "Update the version number and try again.";\
		exit 1;\
	fi
	$(PYTHON) setup.py bdist_wheel upload
	$(PYTHON) setup.py sdist --formats=zip,gztar,bztar upload
	git tag $(PROJ)-`$(PYTHON) setup.py -V`
	git push
	git push --tags
