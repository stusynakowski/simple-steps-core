# streamlit-right-sidebar

A collapsible Streamlit sidebar docked to the **right** edge of the app, mirroring
the API and look-and-feel of `st.sidebar`.

## Installation

```bash
pip install "streamlit-right-sidebar @ git+https://github.com/stuartsynakowski/streamlit-components.git#subdirectory=components/right_sidebar"
```

The prebuilt frontend assets ship with the package, so no Node.js is required.

## How it works

Streamlit custom components render inside an isolated iframe, so they can't
directly host other native Streamlit widgets. To get a real sidebar — one
that can contain any Streamlit widget — this package combines two pieces:

- A plain Python context manager (`right_sidebar`) that creates a keyed
  `st.container` and injects scoped CSS (targeting Streamlit's automatic
  `.st-key-<key>` class) to fix that container to the right edge of the
  viewport, with a slide-in/out transition.
- A tiny custom component (React/TypeScript) used only for the collapse/expand
  handle. It sends the new collapsed state back to Python, which reruns the
  script and updates the CSS.

## Usage

```python
from right_sidebar import right_sidebar

with right_sidebar(width=320):
    st.header("Notes")
    st.text_area("Write something")
```

Use a distinct `key` if you need more than one right sidebar instance:

```python
with right_sidebar(key="notes_panel"):
    ...
```

Customize the toggle handle's icon with an emoji or short text, e.g. to brand it
as a chatbot panel:

```python
with right_sidebar(icon="🤖"):
    ...
```

Use different icons for the collapsed vs. expanded state with `collapse_icon`
and `expand_icon` (each falls back to `icon`, then to the default chevron):

```python
with right_sidebar(collapse_icon="✖️", expand_icon="🤖"):
    ...
```

## Frontend development

```bash
cd right_sidebar/frontend
npm install
npm start
```

With the dev server running on `localhost:3001`, set `_RELEASE = False` in
`right_sidebar/__init__.py` and run the example app:

```bash
uv run streamlit run example/app.py
```

## Building for release

```bash
cd right_sidebar/frontend
npm install
npm run build
```

Then set `_RELEASE = True` in `right_sidebar/__init__.py` (the default) so the
Python package serves the built static assets.
