import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from urllib.parse import urlparse
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
import uuid

# Initialize Firebase
@st.cache_resource
def get_firebase_connection():
    #Chagne the credentials for your project
    cred = credentials.Certificate("serviceAccountKey/firebase-key.json")  # Update with correct path
    firebase_admin.initialize_app(cred)
    return firestore.client()

db = get_firebase_connection()

# Function to fetch button_urls using Selenium
@st.cache_data(ttl=3600)  # Cache the result for 1 hour (adjust as needed)
def get_button_urls(LOOKER_STUDIO_URL):
    if not LOOKER_STUDIO_URL:
        return []  # Ensure function handles empty input

    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Run in headless mode
    chrome_options.add_argument('--disable-gpu')

    # Set up the WebDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(LOOKER_STUDIO_URL)
        time.sleep(5)  # Wait for the page to load

        buttons = driver.find_elements(By.XPATH, "//report-navigation-bar//button")
        if not buttons:
            buttons = driver.find_elements(By.XPATH, "//xap-nav-menu//xap-nav-link")

        if not buttons:
            print("❌ Navigation type not detected!")
            return []

        print("✅ Extracting page data...")

        button_urls = []
        for i, button in enumerate(buttons, start=1):
            button_text = button.text.strip()
            button.click()
            time.sleep(3)

            parsed_url = urlparse(driver.current_url)
            page_id = parsed_url.path.split('/')[-1]

            button_urls.append((i, button_text, page_id))

        return button_urls

    except Exception as e:
        print("⚠️ Error:", e)
        return []

    finally:
        driver.quit()

# UI Title
st.title("Firestore Dashboard Page Manager")

# Input for Looker Studio URL
LOOKER_STUDIO_URL = st.text_input("Enter Looker Studio URL", "")

# Fetch button_urls only once
if LOOKER_STUDIO_URL:
    button_urls = get_button_urls(LOOKER_STUDIO_URL)
    # Extract report_id using regex
    match = re.search(r"reporting/([a-zA-Z0-9\-]+)/page", LOOKER_STUDIO_URL)

    if match:
        report_id = match.group(1)
    else:
        print("Report ID not found")

else:
    button_urls = []

# Display button_urls for debugging
# st.write("Extracted Button URLs:", button_urls)

# Initialize session state for each page number
if 'page_data' not in st.session_state:
    st.session_state.page_data = {str(i[0]): {} for i in button_urls}  # Initialize for each page number

# Ask user where to add a page
page_type = st.radio("Where do you want to add a page?", ["Navigation Document", "Dropdown Folder", "Dashoard Pages"])

# ------------------ NEW TOP-LEVEL PAGE ------------------
if page_type == "Navigation Document":
    st.subheader("➕ Add new navigation document")

    # Fetch available dashboard UIDs from Firestore
    dashboard_docs = db.collection("dashboards").stream()
    dashboard_uids = [doc.id for doc in dashboard_docs]

    dashboard_uids.insert(0, "Create DashboardUid")
    
    dashboard_name = st.text_input("dashboard_name (e.g., Home)", value=st.session_state.page_data.get('dashboard_name', ''))
    dashboard_number = st.number_input("dashboard_number (Number)", min_value=0, step=1, format="%d", value=st.session_state.page_data.get('dashboard_number', 0))  
    dashboard_uid = st.selectbox("Select Dashboard UID", options=dashboard_uids, index=None)
    if dashboard_uid == "Create DashboardUid":
        if "manual_dashboard_uid" not in st.session_state:
            st.session_state["manual_dashboard_uid"] = ""
        col1, col2 = st.columns([3, 1])

        with col1:
            dashboard_uid = st.text_input("Enter New Dashboard UID", value=st.session_state["manual_dashboard_uid"], key="manual_dashboard_uid_input")
        with col2:
            if st.button("Generate Auto ID"):
                st.session_state["manual_dashboard_uid"] = str(uuid.uuid4())[:20]  # Generate an 8-character UID
                st.rerun()


    if st.button("Create Page"):
        db.collection("dashboards").document(dashboard_uid).set({
            "dashboardName": dashboard_name if dashboard_name else None,
            "dashboardNumber": int(dashboard_number),
            "dashboardUid": dashboard_uid if dashboard_uid else None
        })
        st.success(f"✅ Top-level page '{dashboard_name}' added!")
        st.session_state.page_data = {}  # Clear session state after creation

# ------------------ DROPDOWN PAGES ------------------
elif page_type == "Dropdown Folder":
    st.subheader("Add a New Dropdown Folder")

    # Step 1: Fetch and select the parent dashboard
    dashboards = [doc.id for doc in db.collection("dashboards").stream()]
    
    if not dashboards:
        st.warning("⚠ No dashboards found! Please add a top-level document first.")
    else:
        parent_dashboard = st.selectbox("📌 Select Navigation Document", dashboards, index=None)

        # Step 2: Now, display input fields with empty values
        advertiser = st.text_input("advertiser", value=st.session_state.page_data.get('advertiser', ''))
        depth = st.number_input("depth", min_value=0, step=1, format="%d", value=st.session_state.page_data.get('depth', 0))  
        icon_name = st.text_input("iconName", value=st.session_state.page_data.get('icon_name', ''))
        page_name = st.text_input("pageName", value=st.session_state.page_data.get('page_name', ''))
        page_number = st.number_input("pageNumber", min_value=0, step=1, format="%d", value=st.session_state.page_data.get('page_number', 0))
        
        if "manual_page_uid" not in st.session_state:
            st.session_state["manual_page_uid"] = ""
        
        # Fetch existing page UIDs under the selected parent dashboard
        existing_pages = db.collection("dashboards").document(parent_dashboard).collection("pages").stream()
        page_uids = [doc.id for doc in existing_pages]

        page_uids.insert(0, "Create PageUid")
        page_uid = st.selectbox("Select Page UID", options=page_uids, index=None)

        if page_uid == "Create PageUid":
            col1, col2 = st.columns([3, 1])        
        
            with col1:
                page_uid = st.text_input("Enter New Page UID", value=st.session_state["manual_page_uid"], key="manual_page_uid_input")

            with col2:
                if st.button("Generate Auto ID"):
                    st.session_state["manual_page_uid"] = str(uuid.uuid4())[:20]  # Generate 8-character UID
                    st.rerun()  # Rerun to update input field

        # Fetch existing sub-pages under the selected parent dashboard
        
        existing_pages = db.collection("dashboards").document(parent_dashboard).collection("pages").stream()
        depth_eligible_parents = [""]  # Default empty option
        for doc in existing_pages:
            page_data = doc.to_dict()
            depth_eligible_parents.append(page_data.get("pageUid", ""))

        # Step 3: Let user select parent from eligible depths
        parent_uid = st.selectbox("parent", depth_eligible_parents, index=depth_eligible_parents.index(st.session_state.page_data.get('parent_uid', '')))


        path = st.text_input("path", value=st.session_state.page_data.get('path', ''))

        vis_name = st.text_input("visName", value=st.session_state.page_data.get('vis_name', ''))
        vis_page_uid = st.text_input("visPageUid", value=st.session_state.page_data.get('vis_page_uid', ''))
        vis_uid = st.text_input("visUid", value=st.session_state.page_data.get('vis_uid', ''))

        # Step 4: Button to add the new dropdown page
        if st.button("Create Page in Dropdown"):
            page_data = {
                "advertiser": advertiser if advertiser else None,
                "depth": int(depth),
                "iconName": icon_name if icon_name else None,
                "pageName": page_name if page_name else None,
                "pageNumber": int(page_number),
                "pageUid": page_uid if page_uid else None,
                "parent": parent_uid if parent_uid else None,  # Selected from dropdown
                "path": path if path else None,
                "visualizations": [{
                    "visName": vis_name if vis_name else None,
                    "visPageUid": vis_page_uid if vis_page_uid else None,
                    "visUid": vis_uid if vis_uid else None
                }]
            }

            # Step 5: Store the new page under the selected dashboard
            db.collection("dashboards").document(parent_dashboard).collection("pages").document(page_uid).set(page_data)

            st.success(f"✅ New page '{page_name}' added under '{parent_dashboard}'!")
            st.session_state.page_data = {}  # Clear session state after creation

# ------------------ DASHBOARD PAGES ------------------
elif page_type == "Dashoard Pages":
    st.subheader("📑 Add Dashboard pages")

    # Fetch all top-level pages (dashboards)
    dashboards = [doc.id for doc in db.collection("dashboards").stream()]
    
    if not dashboards:
        st.warning("⚠ No dashboards found! Please add a top-level page first.")
    else:
        parent_dashboard = st.selectbox("📌 Select Navigation Document", dashboards, 
                                        index=None)

        advertiser = st.text_input("advertiser", value=st.session_state.page_data.get('advertiser', ''))
        depth = st.number_input("depth", min_value=0, step=1, format="%d", 
                                value=st.session_state.page_data.get('depth', 0))  
        icon_name = st.text_input("iconName", value=st.session_state.page_data.get('icon_name', ''))

        # Fetch all existing pages under the selected dashboard
        existing_pages = db.collection("dashboards").document(parent_dashboard).collection("pages").stream()        

        # Filter pages by depth
        depth_eligible_parents = [""]  
        for doc in existing_pages:
            page_data = doc.to_dict()
            if "depth" in page_data and page_data["depth"] in range(0, depth):  
                depth_eligible_parents.append(page_data["pageUid"])

        # Parent selection dropdown
        parent_uid = st.selectbox("parent", depth_eligible_parents, 
                                  index=depth_eligible_parents.index(st.session_state.page_data.get('parent_uid', '')))
        
        # Store page_number persistently
        st.subheader("Select Page Number")  
        selected_page_number = st.selectbox("pageNumber", [str(i[0]) for i in button_urls], 
                                            index=[str(i[0]) for i in button_urls].index(st.session_state.page_data.get('selected_page_number', '1')))

        # Initialize selected page data in session state
        if selected_page_number not in st.session_state.page_data:
            st.session_state.page_data[selected_page_number] = {}

        # Autofill only pageName based on selected pageNumber
        selected_page = next((i for i in button_urls if str(i[0]) == selected_page_number), None)
        if selected_page:
            default_page_name = selected_page[1]
            default_vis_page_uid = selected_page[2]
            default_vis_name = selected_page[1]
            default_page_uid = None
        else:
            default_page_name = ""
            default_vis_page_uid = ""
            default_vis_name = ""

        # Update session state defaults if not already set
        page_name = st.text_input("pageName", value=st.session_state.page_data[selected_page_number].get('page_name', default_page_name), key=f"page_name_{selected_page_number}")  
        page_number = st.number_input("pageNumber", min_value=0, step=1, format="%d", value=int(selected_page_number))  

        if "manual_page_uid" not in st.session_state:
            st.session_state["manual_page_uid"] = ""

        # Fetch existing page UIDs under the selected parent dashboard
        existing_pages = db.collection("dashboards").document(parent_dashboard).collection("pages").stream()
        page_uids = [doc.id for doc in existing_pages]
        page_uids.insert(0, "Create PageUid")
        select_page_uid_key = f"select_page_uid_{selected_page_number}"
        page_uid = st.selectbox("Select Page UID", options=page_uids, index=None, key=select_page_uid_key)
        if f"manual_page_uid_{selected_page_number}" not in st.session_state:
            st.session_state[f"manual_page_uid_{selected_page_number}"] = ""

        if page_uid == "Create PageUid":
            # st.session_state[f"manual_page_uid_{selected_page_number}"] = ""  # Initialize for the selected page number

            col1, col2 = st.columns([3, 1])        
            with col1:
                page_uid = st.text_input(f"Enter New Page UID ", value=st.session_state[f"manual_page_uid_{selected_page_number}"], key=f"manual_page_uid_input_{selected_page_number}")

            with col2:
                if st.button(f"Generate Auto ID"):
                    st.session_state[f"manual_page_uid_{selected_page_number}"] = str(uuid.uuid4())[:20] # Generate a 20-character UID
                    st.rerun()  # Rerun to update input field


        # Auto-generate path but allow editing
        default_path = f"/<campaign_type>_<advertiser>_<year>_{default_page_name.replace(' ', '_').lower()}"
        path = st.text_input("path", value=st.session_state.page_data[selected_page_number].get('path', default_path), key=f"path_{selected_page_number}")  

        # Visualization fields
        vis_name = st.text_input("visName", value=st.session_state.page_data[selected_page_number].get('vis_name', default_vis_name), key=f"vis_name_{selected_page_number}")  
        vis_page_uid = st.text_input("visPageUid", value=st.session_state.page_data[selected_page_number].get('vis_page_uid', default_vis_page_uid), key=f"vis_page_uid_{selected_page_number}")  
        vis_uid = st.text_input("visUid", value=report_id)

        # Update session state when fields are modified
        st.session_state.page_data[selected_page_number] = {
            'parent_dashboard': parent_dashboard,
            'advertiser': advertiser,
            'depth': depth,
            'icon_name': icon_name,
            'parent_uid': parent_uid,
            'selected_page_number': selected_page_number,
            'page_name': page_name,
            'page_number': page_number,
            'page_uid': page_uid,
            'path': path,
            'vis_name': vis_name,
            'vis_page_uid': vis_page_uid,
            'vis_uid': vis_uid
        }

        if st.button("Create Sub-Page"):
            page_data = {
                "advertiser": advertiser if advertiser else None,
                "depth": int(depth),
                "iconName": icon_name if icon_name else None,
                "pageName": page_name if page_name else None,
                "pageNumber": int(page_number),
                "pageUid": page_uid if page_uid else None,
                "parent": parent_uid if parent_uid else None,  
                "path": path if path else None,  
                "visualizations": [{
                    "visName": vis_name if vis_name else None,  
                    "visPageUid": vis_page_uid if vis_page_uid else None,  
                    "visUid": vis_uid if vis_uid else None
                }]  
            }

            db.collection("dashboards").document(parent_dashboard).collection("pages").document(page_uid).set(page_data)

            st.success(f"✅ Sub-page '{page_name}' added under '{parent_dashboard}'!")