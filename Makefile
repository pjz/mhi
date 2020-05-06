
PROJ=mhi

VENV=./env
PIP=$(VENV)/bin/pip
PYTEST=$(VENV)/bin/pytest
PYTEST_ARGS=-v --timeout=60 $(PYTEST_EXTRA)
PYTHON=python


venv $(VENV):
	virtualenv --python=python3 $(VENV)
	$(PIP) install -e .

test: env
	if [ ! -f $(PYTEST) ]; then \
		$(PIP) install pytest ;\
		$(PIP) install pytest-runfailed ;\
		$(PIP) install pytest-timeout ;\
		$(PIP) install mock ;\
	fi
	cd tests && ../$(PYTEST) $(PYTEST_ARGS)

testf: env
	cd tests && ../$(PYTEST) --failed $(PYTEST_ARGS)

testf-clean: env clean-testf
	cd tests && ../$(PYTEST) --failed $(PYTEST_ARGS)

clean-testf:
	rm -rf tests/.pytest

clean: clean-testf
	rm -rf env build dist *.egg-info
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
	@if [ `git status --short | wc -l` != 0 ]; then\
		echo "Uncommited code. Aborting." ;\
		exit 1;\
	fi
	$(PYTHON) setup.py bdist_wheel upload
	$(PYTHON) setup.py sdist --formats=zip,gztar,bztar upload
	git tag $(PROJ)-`$(PYTHON) setup.py -V`
	git push
	git push --tags
