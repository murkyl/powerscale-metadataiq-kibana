VER:=$(shell grep __version__ translate/translate.py | head -n 1 | sed -E 's/.*"(.*)"/\1/')
all: translate_release

translate: clean
	mkdir -p build
	mkdir -p dist
	cd translate; zip -r ../build/translate.pyz *
	zip -r build/translate.pyz *.md
	zip -r build/translate.pyz languages
	zip -r build/translate.pyz templates
	echo '#!/usr/bin/env python3' | cat - build/translate.pyz > dist/translate.pyz
	chmod a+x dist/translate.pyz

translate_release: translate
	mkdir -p releases
	cp dist/translate.pyz releases/
	cp dist/translate.pyz releases/translate-$(VER).pyz

.PHONY: clean
clean: clean_compiled
	-rm -rf build
	-rm -rf dist
	-rm -rf *.egg-info

.PHONY: clean_compiled
clean_compiled:
	find . -name __pycache__ -type d -exec rm -rf {} +
	find . -name *.pyc -delete

.PHONY: clean_releases
clean_releases:
	-rm -rf releases

.PHONY: format
format:
	find . -name \*.py -exec black {} +