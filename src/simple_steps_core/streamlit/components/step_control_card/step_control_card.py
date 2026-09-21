import streamlit as st
import streamlit_extras as ste


#from streamlit_extras.resizable_columns import resizable_columns

# session state call backs:



#


#streamlit = step_card()


# what do 





_='''
    with st.expander("Step Control Card",type="compact"):
        # Add your step control card content here
        #st.write("Step control card content goes here.")
        #with st.container(gap="xxsmall"):
        col1, col2, col3 = ste.resizable_columns(3,border=False,min_width=10,gap="0.25rem")

        with col1:
            #st.button("Previous Step")
            with st.expander("Exec Col"):
                st.write("Exec Col content goes here.")
        with col2:
            #st.button("Current Step")
            with st.expander("Orch "):
                st.write("Orch content goes here.")
        with col3:
            #st.button("Next Step")
            with st.expander("Cal"):
                st.write("Cal content goes here.")


    from streamlit_extras.steps import steps

    h_steps = steps(
        ["Upload", "Review", "Submit"],
        horizontal=True,
        icons=range(1, 4),
        key="demo_hn",
    )

    with h_steps[0]:
        st.info("Upload your files here.")
        if st.button("Next", key="hn_next_0"):
            h_steps.next()

    with h_steps[1]:
        st.info("Review your submission.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Back", key="hn_back_1"):
                h_steps.previous()
        with c2:
            if st.button("Next", key="hn_next_1"):
                h_steps.next()

    with h_steps[2]:
        st.info("Click submit to finish.")
        if st.button("Start over", key="hn_reset"):
            h_steps.reset()


    # streamlit container()

'''