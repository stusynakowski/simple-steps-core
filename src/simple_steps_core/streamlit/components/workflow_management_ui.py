import streamlit as st
from itertools import count





# render workflow manager UI

# load current session from session manager
# this will give you current workflow
# possible containing tools and registries
# current current tools and resoures





st.set_page_config(page_title="Horizontal Containers", layout="wide")

# current workflows


# what does the session_state contain

# basically workflows
# each button 

# load the workflow


# backend methods needed

# loading simple steps session

# running steps

# 
# session_state workflow ["workflow"]






CARDS_KEY = "cards_row"
CARD_WIDTH = 220

# Force the horizontal row to scroll instead of wrap/shrink its children.
st.markdown(
    f"""
    <style>
    div.st-key-{CARDS_KEY} {{
        overflow-x: auto;
        overflow-y: hidden;
    }}
    div.st-key-{CARDS_KEY} > div {{
        flex-wrap: nowrap !important;
        min-width: max-content;
    }}
    div.st-key-{CARDS_KEY} > div > div {{
        flex-shrink: 0 !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

if "id_gen" not in st.session_state:
    st.session_state.id_gen = count(1)
if "containers" not in st.session_state:
    # each: {"id": str, "expanded": bool, "group": str | None}
    st.session_state.containers = []
if "group_gen" not in st.session_state:
    st.session_state.group_gen = count(1)
if "selected" not in st.session_state:
    st.session_state.selected = set()


# workflow managment operations
def add_step():
    cid = f"C{next(st.session_state.id_gen)}"
    st.session_state.containers.append({"id": cid, "expanded": True, "group": None})
    # this will append the step to the UI


def remove_step():
    st.session_state.containers = [
        c for c in st.session_state.containers if c["id"] not in st.session_state.selected
    ]
    st.session_state.selected.clear()
    # need to delete step from workflow

def swap_step():
    selected = list(st.session_state.selected)

def group_steps():
    if len(st.session_state.selected) < 2:
        return
    gid = f"G{next(st.session_state.group_gen)}"
    for c in st.session_state.containers:
        if c["id"] in st.session_state.selected:
            c["group"] = gid
    st.session_state.selected.clear()


def ungroup_steps():
    for c in st.session_state.containers:
        if c["id"] in st.session_state.selected:
            c["group"] = None
    st.session_state.selected.clear()


def stage_step():
    #psomething herror
    # this will return what the output should be
    print("hellow")

def run_step():
    # this will
    print("this will run a particular step")




def toggle_all(expanded: bool):
    for c in st.session_state.containers:
        if not st.session_state.selected or c["id"] in st.session_state.selected:
            c["expanded"] = expanded




# --- Toolbar ---
with st.expander("Workflow Manager",expanded=True):

    step_selection_col,step_managment_col=st.columns([5,1])
    with step_selection_col:
        with st.container(horizontal_alignment="left",vertical_alignment="top"):
            steps = [f"Step {c['id']}" for c in st.session_state.containers]

            # should contain the list of current steps in the workflow update session_states
            selected_step=st.segmented_control("Current Steps", options=steps,selection_mode="multi")
            st.session_state.selected = {s.split(" ")[1] for s in selected_step}
            with st.container(horizontal=True,vertical_alignment="top",horizontal_alignment="left"):
                st.button(":material/add_circle_outline: Add", on_click=add_step)
                with st.popover(":material/remove_circle_outline: Remove"):
                    st.write("Are you sure you want to remove the selected step(s)?")
                with st.popover(":material/swap_horiz: Swap"):
                    st.write("Are you sure you want to swap the selected step(s)?")
                #st.pills("manage_steps",label_visibility="collapsed", options=[":material/add_circle_outline: Add", ":material/remove_circle_outline: Remove Step", ":material/swap_horiz: Swap Step"])
    with step_managment_col:
        with st.container(horizontal=True, gap="xxsmall"):
            with st.popover("Group Steps into Stages"):
                st.button(":material/merge_type: Group selected", on_click=group_steps)
                st.button(":material/call_split: Ungroup selected", on_click=ungroup_steps)

    #st.divider()
    st.write("Run Workflow")
    with st.container(horizontal=True, gap="xxsmall"):
        
        st.button(":material/play_arrow:",type="primary")
        st.button(":material/refresh:")
        st.button(":material/fast_forward:")
        st.write(" status bar here")
        # there will be a progress bar here

def render_step(c: dict):
    #step_container= st.container( key=f"card_{c['id']}")
    exec_col,tool_bar_col= st.columns(2)
    with tool_bar_col:
        with st.container(horizontal=True, gap=None,vertical_alignment="top",horizontal_alignment="right"):
                # UI managed components for current session
                st.segmented_control("Step Details",label_visibility="collapsed", options=[":material/function:", ":material/step:", ":material/dataset:", ":material/settings:"], key=f"segmented_{c['id']}")
    with exec_col:

        with st.container(horizontal=True, gap="xxsmall", horizontal_alignment="left", vertical_alignment="top"):
            # for running the step
            st.button(":material/play_arrow:",key=f"play_{c['id']}")
            st.button(":material/refresh:",key=f"refresh_{c['id']}")
            st.button(":material/fast_forward:",key=f"fast_forward_{c['id']}")
        # hiding the UI for the function status
        
        

    with st.expander(" :material/function: Operation Details"):
        st.write("Details about the operation (placeholder)")
    with st.expander(" :material/dataset: Output"):
        st.write("Output of the operation (placeholder)")
        
        
            


# --- Horizontal layout of containers, grouping preserved by insertion order ---
with st.expander("Step Manager", expanded=True):
    with st.container(
        horizontal=True,
        wrap=False,
        horizontal_alignment="left",
        gap="xxsmall",
        key=CARDS_KEY,
        
    ):
        i = 0
        items = st.session_state.containers
        while i < len(items):
            c = items[i]
            if c["group"] is None:
                
                with st.expander(f"Step {c['id']}", expanded=True, key=f"step_{c['id']}"):
                    render_step(c)
                i += 1
            else:
                gid = c["group"]
                with st.expander(f"Group {gid}", expanded=True, key=f"stage_{gid}"):
                    
                        with st.container(horizontal=True, wrap=False):
                            while i < len(items) and items[i]["group"] == gid:
                                with st.expander(f"Step {items[i]['id']}", expanded=True, key=f"step_{items[i]['id']}"):
                                    render_step(items[i])
                                i += 1
