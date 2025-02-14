from translate import main

# __name__ will be __main__ when run directly from the Python interpreter.
# __file__ will be None if the Python files are combined into a ZIP file and executed there
if __name__ == "__main__" or __file__ is None:
    main()
