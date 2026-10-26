from importlib.resources import as_file, files
from runpy import run_path

with as_file(files("code_review_agent").joinpath("streamlit_app.py")) as page:
    run_path(str(page), run_name="__main__")
