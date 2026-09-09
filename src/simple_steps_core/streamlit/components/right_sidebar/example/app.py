import streamlit as st

from right_sidebar import right_sidebar

st.title("right_sidebar demo")
st.write(
    "This is the main app content. Compare the native sidebar on the left "
    "with the custom right_sidebar on the right."
)

with st.sidebar:
    st.header("Left sidebar (native)")
    st.write("This is `st.sidebar`, for comparison.")
    st.text_input("Name", key="left_name")
    st.slider("Pick a value", 0, 100, key="left_slider")

for i in range(30):
    st.write(f"Main content line {i + 1}")

with right_sidebar(width=320, icon=":material/smart_toy:", initial_collapsed=True):
    st.header("Right sidebar")
    st.write("Any Streamlit widget works in here, same as `st.sidebar`.")
    name = st.text_input("Name")
    st.slider("Pick a value", 0, 100)
    if name:
        st.write(f"Hello, {name}!")
