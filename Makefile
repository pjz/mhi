
PROJ=mhi

include reqs/Makefile.piptools

PYTHON=python

DEV_ENV=.pip_syncd

default::
	@echo "dev - set up the dev venv"
	@echo "test - run tests"
	@echo "testf - run tests until first fail"
	@echo "wheel - build a python wheel"
	@echo "release - release the current version to pypi"
	@echo "clean - nuke build artifacts"


$(DEV_ENV): $(DEPS)
	pip-sync $(DEPS)
	touch $(DEV_ENV)

.PHONY: dev
dev: $(DEV_ENV)

PYTEST_ARGS=-v --timeout=60 $(PYTEST_EXTRA)

test: $(DEV_ENV)
	pytest tests $(PYTEST_ARGS)

testf: PYTEST_EXTRA=--log-cli-level=DEBUG -ff
testf: test

clean:
	rm -rf tests/.pytest
	rm -rf $(DEV_ENV) build dist *.egg-info
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
