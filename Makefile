
PROJ=$(shell grep ^name pyproject.toml | cut -d\" -f2)
VERSION=$(shell grep ^version pyproject.toml | cut -d\" -f2)

include Makefile.pyproject


default::
	@echo "test - run tests"
	@echo "testf - run tests until first fail"
	@echo "git-release - release the current version to pypi"
	@echo "pypi-release - release the current version to pypi"
	@# from Makefile.pyproject
	@echo "clean - nuke build artifacts"


mypy pylint test coverage.xml coverage-html.zip: export PYTHONWARNINGS=ignore,default:::$(PROJ)

CODECOV_OUTPUT=--cov-report term

pylint: $(DEV_ENV)
	pytest $(PROJ) \
		--pylint --pylint-rcfile=.pylintrc \
		--pylint-error-types=EF \
		-m pylint \
		--cache-clear

.coverage:
	@echo "You must run tests first!"
	exit 1

coverage-html.zip: .coverage
	coverage html -d htmlconv
	cd htmlconv && zip -r ../$@ .

coverage.xml: .coverage
	coverage xml

test: $(DEV_ENV)
	pytest tests $(PYTEST_ARGS) $(PYTEST_EXTRA)

testf: PYTEST_EXTRA=--log-cli-level=DEBUG -lx --ff
testf: test

.PHONY: mypy
mypy:
	mypy --non-interactive --install-types --ignore-missing-imports $(PROJ)
	#pytest --mypy -m mypy $(PROJ)
	#mypy --check-untyped-defs $(PROJ)

.PHONY: coverage
coverage:
	pytest --cov=$(PROJ) $(CODECOV_OUTPUT) tests $(PYTEST_ARGS)


.PHONY: not-dirty
not-dirty:
	@if [ `git status --short | wc -l` != 0 ]; then\
	    echo "Uncommited code. Aborting." ;\
	    exit 1;\
	fi

.PHONY: git-release
git-release: wheel not-dirty
	@if [ `git rev-parse --abbrev-ref HEAD` != main ]; then \
	echo "You can only do a release from the main branch.";\
	    exit 1;\
	fi
	@if git tag | grep -q ^$(VERSION) ; then \
	    echo "Already released this version.";\
	    echo "Update the version number and try again.";\
	    exit 1;\
        fi
	git push &&\
	git tag $(SIGN) $(VERSION) -m "Release v$(VERSION)" &&\
	git push --tags &&\
	git checkout release &&\
	git merge $(VERSION) &&\
	git push && git checkout main
	@echo "Released! Note you're now on the 'main' branch."

.PHONY: pypi-release
pypi-release: wheel
	python -m build
	twine upload dist/$(PROJ)-$(VERSION)*

