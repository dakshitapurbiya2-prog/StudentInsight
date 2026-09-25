"""Teacher Dashboard view with class overview, marks entry, PDF extraction, and student performance drill-down."""

import streamlit as st
import pandas as pd
from typing import Optional
from app.frontend.mock_data import (
    get_all_students,
    get_teacher_classes,
    get_class_students,
    get_pending_marks_entry,
    get_extracted_marks_from_pdf,
)
from app.frontend.dashboards.student_dashboard import render_student_dashboard
from app.frontend.dashboards.pdf_upload_tab import render_pdf_upload_tab


def render_teacher_dashboard(teacher_id: Optional[str] = "TCH001"):
    st.title("≡ƒæ⌐ΓÇì≡ƒÅ½ Teacher Dashboard")

    active_teacher_id = teacher_id or "TCH001"

    # --- Sidebar controls ---
    st.sidebar.subheader("Teacher Controls")
    classes = get_teacher_classes(active_teacher_id)
    class_options = [f"{c['class_name']} ({c['subject']})" for c in classes]
    selected_class_label = st.sidebar.selectbox("Select Class", class_options)
    selected_class_idx = class_options.index(selected_class_label)
    selected_class = classes[selected_class_idx]

    exam_options = ["Unit Test 1", "Mid Term", "Unit Test 2", "Final Term"]
    selected_exam = st.sidebar.selectbox("Select Exam", exam_options)

    # --- Tabs ---
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "≡ƒôï Class Overview",
            "Γ£Å∩╕Å Manual Entry",
            "≡ƒôä PDF Upload",
            "≡ƒöì Student Performance",
        ]
    )

    # ===== Tab 1: Class Overview =====
    with tab1:
        st.subheader("Class Overview")
        col1, col2, col3 = st.columns(3)
        col1.metric("Class Name", selected_class["class_name"])
        col2.metric("Subject", selected_class["subject"])
        col3.metric("Number of Students", selected_class["num_students"])

        st.markdown("##### Student List")
        students_df = get_class_students(selected_class["class_name"])
        st.dataframe(students_df, use_container_width=True, hide_index=True)

    # ===== Tab 2: Manual Entry =====
    with tab2:
        st.subheader("Enter Marks Manually")
        marks_df = get_pending_marks_entry(
            selected_class["class_name"], selected_exam
        )
        edited_df = st.data_editor(
            marks_df,
            column_config={
                "marks": st.column_config.NumberColumn(
                    "Marks",
                    help="Enter marks from 0 to 100",
                    min_value=0,
                    max_value=100,
                    step=1,
                )
            },
            disabled=["student_id", "name", "roll_number"],
            hide_index=True,
            use_container_width=True,
        )

        if st.button("Save Marks"):
            st.success("Marks saved successfully!")

    # ===== Tab 3: PDF Upload (Real Import Workflow) =====
    with tab3:
        # Determine teacher display name for the audit trail
        teacher_display_name = "Teacher"
        try:
            from app.frontend.auth import get_current_user
            user = get_current_user()
            if user and user.name:
                teacher_display_name = user.name
        except Exception:
            pass

        render_pdf_upload_tab(teacher_name=teacher_display_name)

    # ===== Tab 4: Student Performance Search & Drill-Down =====
    with tab4:
        st.subheader("Individual Student Performance")
        all_students = get_all_students()

        # Search bar for students
        search_col, select_col = st.columns([1.5, 2])
        with search_col:
            search_query = st.text_input(
                "Search Student by Name or ID",
                placeholder="e.g. Aarav, Ananya, STU003...",
                key="teacher_student_search",
            )

        # Filter students based on search
        if search_query.strip():
            filtered_students = [
                s
                for s in all_students
                if search_query.lower() in s["name"].lower()
                or search_query.lower() in s["student_id"].lower()
            ]
        else:
            filtered_students = all_students

        if not filtered_students:
            st.warning(f"No students matching '{search_query}'. Showing all students.")
            filtered_students = all_students

        with select_col:
            student_labels = [
                f"{s['name']} ({s['student_id']}) ΓÇö Class {s['class']}"
                for s in filtered_students
            ]
            selected_student_label = st.selectbox(
                "Select Student to Inspect",
                student_labels,
                index=0,
                key="teacher_selected_student",
            )
            selected_student_idx = student_labels.index(selected_student_label)
            selected_student_id = filtered_students[selected_student_idx]["student_id"]

        st.divider()

        # Render complete student dashboard drill-down for the chosen student
        render_student_dashboard(
            student_id=selected_student_id,
            is_student_role=False,
            show_title=False,
        )
