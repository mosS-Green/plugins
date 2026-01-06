import asyncio
import os
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
)

from app import BOT, Message

# Configuration
LOGIN_URL = "https://srs.zo-apps.org/auth/login"
LISTING_URL = "https://srs.zo-apps.org/satsang/listing"

# Update these credentials via environment variables or modify here
EMAIL = os.environ.get("SRS_EMAIL", "your_email@example.com")
PASSWORD = os.environ.get("SRS_PASSWORD", "your_password")


def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    # options.add_argument("--headless") # Commented out by default, user preference
    driver = webdriver.Chrome(options=options)
    return driver


def login(driver, email, password):
    """Logs into the application."""
    print("Logging in...")
    driver.get(LOGIN_URL)

    try:
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "email"))
        )
        email_field.clear()
        email_field.send_keys(email)

        pass_field = driver.find_element(By.NAME, "password")
        pass_field.clear()
        pass_field.send_keys(password)

        # Click login button (found via value attribute or class)
        submit_btn = driver.find_element(By.XPATH, "//input[@value='Login']")
        submit_btn.click()

        # Wait for redirect to dashboard or listing
        WebDriverWait(driver, 10).until(EC.url_changes(LOGIN_URL))
        print("Login successful.")
    except Exception as e:
        print(f"Login failed: {e}")
        driver.quit()
        raise e


def select_bootstrap_dropdown(driver, modal, data_id, value):
    """
    Handles the custom Bootstrap dropdowns found in the HTML.
    These are <button data-id="..."> followed by a div.dropdown-menu
    """
    try:
        # Locate the button that triggers the dropdown within the modal
        # Using XPath to ensure we target the button specifically by its data-id attribute
        dropdown_btn = modal.find_element(By.XPATH, f".//button[@data-id='{data_id}']")

        # Scroll to element to ensure it's clickable
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", dropdown_btn
        )
        time.sleep(0.5)  # Short pause for stability

        dropdown_btn.click()

        # Wait for the dropdown menu to expand (it gets class 'show')
        # We look for the span text inside the specifically opened dropdown
        option_xpath = f"//div[contains(@class, 'dropdown-menu') and contains(@class, 'show')]//span[contains(text(), '{value}')]"

        option = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, option_xpath))
        )
        option.click()
        print(f"Selected '{value}' for {data_id}")

    except Exception as e:
        print(f"Error selecting '{value}' for dropdown '{data_id}': {e}")
        # Not raising here to allow continuation if possible, or maybe should raise?
        # User script printed error, I'll follow that usage.


def fill_satsang_form(driver, data):
    """
    Navigate to listing and fills the Add Satsang Modal.
    """
    print("Navigating to Satsang Listing...")
    driver.get(LISTING_URL)

    try:
        # 1. Open the Modal
        # Found via class "add_functionary" and text "ADD SATSANG"
        add_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(@class, 'add_functionary') and contains(text(), 'ADD SATSANG')]",
                )
            )
        )
        # Using JS click often safer for such buttons
        driver.execute_script("arguments[0].click();", add_btn)

        # 2. Wait for Modal Visibility
        modal = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.ID, "add_satsang_modal"))
        )
        print("Modal opened.")
        time.sleep(1)  # Allow animations to finish

        # --- FILL FORM FIELDS ---

        # 1. Zone, State, Area, Centre (Bootstrap Dropdowns)
        if "zone" in data:
            select_bootstrap_dropdown(driver, modal, "zone_id", data["zone"])
        if "state" in data:
            select_bootstrap_dropdown(driver, modal, "state_id", data["state"])
        if "area" in data:
            select_bootstrap_dropdown(driver, modal, "area_id", data["area"])
        if "centre" in data:
            select_bootstrap_dropdown(driver, modal, "centre_id", data["centre"])

        # 2. Satsang Type & Session
        if "satsang_type" in data:
            select_bootstrap_dropdown(
                driver, modal, "satsang_type", data["satsang_type"]
            )

        if "session" in data:
            select_bootstrap_dropdown(driver, modal, "satsang_session", data["session"])

        # 3. Date
        if "date" in data:
            date_input = modal.find_element(By.ID, "satsang_date")
            date_input.send_keys(data["date"])
            driver.execute_script(
                "arguments[0].dispatchEvent(new Event('change'))", date_input
            )

        # 4. Sangat Counts (Conditional based on Type)
        # Type: MAIN_SATSANG
        if data.get("satsang_type") == "MAIN SATSANG":
            if "gents" in data:
                modal.find_element(By.ID, "Gents").send_keys(data["gents"])
            if "ladies" in data:
                modal.find_element(By.ID, "Ladies").send_keys(data["ladies"])

        # Type: BAAL_SATSANG
        elif data.get("satsang_type") == "BAAL SATSANG":
            if "children" in data:
                modal.find_element(By.ID, "Children").send_keys(data["children"])

            if "guide_boys" in data:
                modal.find_element(By.ID, "guide_boys_count").send_keys(
                    data["guide_boys"]
                )
            if "guide_girls" in data:
                modal.find_element(By.ID, "guide_girls_count").send_keys(
                    data["guide_girls"]
                )

        # 5. Time & Duration
        if "start_time" in data:
            modal.find_element(By.ID, "start_time").send_keys(data["start_time"])

        if "duration_hour" in data:
            modal.find_element(By.ID, "duration_hour").send_keys(data["duration_hour"])

        if "duration_minute" in data:
            modal.find_element(By.ID, "duration_minute").send_keys(
                data["duration_minute"]
            )

        # 6. Preacher Details
        if "preacher_type" in data:
            select_bootstrap_dropdown(
                driver, modal, "preacher_type", data["preacher_type"]
            )

        if "preacher_name" in data:
            modal.find_element(By.ID, "preacher_name").send_keys(data["preacher_name"])

        if "preacher_badge" in data:
            modal.find_element(By.ID, "preacher_badge_number").send_keys(
                data["preacher_badge"]
            )

        if "grading" in data:
            select_bootstrap_dropdown(driver, modal, "grading", data["grading"])

        # 7. Pathi Details
        if "pathi_name" in data:
            modal.find_element(By.ID, "pathi_name").send_keys(data["pathi_name"])

        if "pathi_badge" in data:
            modal.find_element(By.ID, "pathi_badge_number").send_keys(
                data["pathi_badge"]
            )

        # 8. Shabad & Saint
        if "shabad" in data:
            modal.find_element(By.ID, "shabad_taken").send_keys(data["shabad"])

        if "saint_name" in data:
            modal.find_element(By.ID, "bani_by").send_keys(data["saint_name"])

        # 9. Language
        if "language" in data:
            select_bootstrap_dropdown(
                driver, modal, "satsang_language", data["language"]
            )

        # 10. Sewadar Details
        if "sewadar_male" in data:
            modal.find_element(By.ID, "sewadar_male_count").send_keys(
                data["sewadar_male"]
            )
        if "sewadar_female" in data:
            modal.find_element(By.ID, "sewadar_female_count").send_keys(
                data["sewadar_female"]
            )

        # 11. Remarks
        if "remarks" in data:
            modal.find_element(By.ID, "satsang_remarks").send_keys(data["remarks"])

        print("Form filled. Submitting...")

        # 12. Submit
        submit_btn = modal.find_element(
            By.CSS_SELECTOR, "input.submitAddEditSatangFormSubmitBtn"
        )
        driver.execute_script("arguments[0].click();", submit_btn)

        time.sleep(3)

    except Exception as e:
        print(f"An error occurred during form filling: {e}")
        # driver.save_screenshot("error_satsang_form.png") # User might not be able to access local file easily, but can be useful for debugging
        raise e


def run_srs_automation(data):
    driver = None
    try:
        driver = get_driver()
        login(driver, EMAIL, PASSWORD)
        fill_satsang_form(driver, data)
        return "Success"
    except Exception as e:
        return f"Error: {e}"
    finally:
        if driver:
            print("Process complete. Closing in 5 seconds...")
            time.sleep(5)
            driver.quit()


def parse_input(text):
    data = {}
    matches = re.findall(r"(\w+)\s*\{(.*?)\}", text)
    for key, value in matches:
        data[key] = value.strip()
    return data


@BOT.add_cmd("srs")
async def srs_cmd(bot: BOT, message: Message):
    text = message.input or (message.replied.text if message.replied else "")

    if not text:
        help_message = (
            "**SRS Form Submission**\n\n"
            "**Usage:**\n"
            "Send or reply with the following format:\n\n"
            "`centre {AFZALGARH (C)}`\n"
            "`satsang_type {MAIN SATSANG}`\n"
            "`session {MORNING}`\n"
            "`date {06-01-2026}`\n"
            "`gents {50}`\n"
            "`ladies {45}`\n"
            "`children {10}`\n"
            "`start_time {09:00}`\n"
            "`duration_hour {0}`\n"
            "`duration_minute {30}`\n"
            "`preacher_type {SATSANG KARTA (SK)}`\n"
            "`preacher_name {Name}`\n"
            "`grading {A}`\n"
            "`pathi_name {Name}`\n"
            "`shabad {Topic}`\n"
            "`saint_name {Saint}`\n"
            "`language {HINDI}`\n"
            "`sewadar_male {5}`\n"
            "`sewadar_female {5}`\n"
            "`remarks {Initial Remarks}`\n"
            "\n"
            "**Defaults if not specified:**\n"
            "- Language: HINDI\n"
            "- Type: MAIN SATSANG\n"
            "- Session: MORNING\n"
            "- Start Time: 09:00\n"
            "- Duration: 0h 30m"
        )
        await message.reply(help_message)
        return

    # Default values
    satsang_data = {
        "language": "HINDI",
        "satsang_type": "MAIN SATSANG",
        "session": "MORNING",
        "start_time": "09:00",
        # Adding some sensible defaults for others to avoid errors if they are mandatory
        "duration_hour": "0",
        "duration_minute": "30",
        "sewadar_male": "0",
        "sewadar_female": "0",
        "gents": "0",
        "ladies": "0",
        "children": "0",
    }

    # Update with parsed user input
    user_data = parse_input(text)
    satsang_data.update(user_data)

    status_msg = await message.reply("Running SRS Automation... Please wait.")

    try:
        # Run blocking selenium code in a separate thread
        result = await asyncio.to_thread(run_srs_automation, satsang_data)

        if result == "Success":
            await status_msg.edit("**SRS Report Submitted Successfully!**")
        else:
            await status_msg.edit(f"**Failed:**\n{result}")

    except Exception as e:
        await status_msg.edit(f"**Error:** {e}")
