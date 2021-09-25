# To package up as executable, run this in command prompt:
# (windows) pyinstaller --onefile --hidden-import=colorama --hidden-import=jinxed.terminfo.vtwin10 --icon=favicon.ico autofill.py
# (macos) pyinstaller --onefile --hidden-import=colorama --hidden-import=inquirer --icon=favicon.ico autofill.py

import colorama
from distlib.compat import raw_input
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import (
    NoAlertPresentException,
    UnexpectedAlertPresentException,
    NoSuchElementException,
    TimeoutException,
    NoSuchFrameException,
)
from selenium.webdriver.support.expected_conditions import invisibility_of_element
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import argparse
import time
import os
import sys
import xml.etree.ElementTree as ET
from numpy import array as np_array, uint8 as np_uint8
from requests import post as requests_post
from requests.exceptions import Timeout as requests_Timeout
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from queue import Queue
from math import floor
from glob import glob


from autofill_utils import currdir, XML_Order

from platform import system

IS_WINDOWS = system() == "Windows"
if IS_WINDOWS:
    from inquirer import List as inquirer_List, prompt as inquirer_prompt
else:
    from enquiries import choose as enquiries_choose
"""
Drive File Info API
https://script.google.com/macros/s/AKfycbw90rkocSdppkEuyVdsTuZNslrhd5zNT3XMgfucNMM1JjhLl-Q/exec

function doPost(e) {
  return (function(id){
    var file = DriveApp.getFileById(id);
    return ContentService
          .createTextOutput(JSON.stringify({
            //result: file.getBlob().getBytes(),
            name: file.getName(),
            mimeType: file.getBlob().getContentType()
          }))
          .setMimeType(ContentService.MimeType.JSON);
  })(e.parameters.id);
}
"""

"""
Drive File Contents API
https://script.google.com/macros/s/AKfycbzzCWc2x3tfQU1Zp45LB1P19FNZE-4njwzfKT5_Rx399h-5dELZWyvf/exec

function doPost(e) {
  return (function(id){
    var file = DriveApp.getFileById(id);
    var size = file.getSize();
    var result = [];
    if (size <= 30000000) {
      result = file.getBlob().getBytes();
    }
    return ContentService
          .createTextOutput(JSON.stringify({
            result: result,
          }))
          .setMimeType(ContentService.MimeType.JSON);
  })(e.parameters.id);
}
"""

# Define the command line argument parser
command_line_argument_parser = argparse.ArgumentParser(description='Make Playing Cards Autofill Script')

command_line_argument_parser.add_argument('-skipsetup', action="store_true", default=False, help='Skip Setup')

command_line_args = command_line_argument_parser.parse_args()

# Disable logging messages for webdriver_manager
os.environ["WDM_LOG_LEVEL"] = "0"

q_front = Queue()
q_back = Queue()
q_cardback = Queue()
q_error = Queue()

TEXT_BOLD = "\033[1m"
TEXT_END = "\033[0m"

# On macOS, os.getcwd() doesn't work as expected - retrieve the executable's directory another way instead

cards_folder = currdir() # + "/images"
# if not os.path.exists(cards_folder):
#    os.mkdir(cards_folder)


def switch_to_frame(driver, frame):
    try:
        driver.switch_to.frame(frame)
    except (NoSuchFrameException, NoSuchElementException):
        pass


def text_to_list(input_text):
    # Helper function to translate strings like "[2, 4, 5, 6]" into lists
    if input_text == "":
        return []
    return [int(x) for x in input_text.strip("][").replace(" ", "").split(",")]


def text_to_list(input_text):
    # Helper function to translate strings like "[2, 4, 5, 6]" into lists
    if input_text == "":
        return []
    return [int(x) for x in input_text.strip("][").replace(" ", "").split(",")]


def fill_cards(bar: tqdm, driver, root):

    if not command_line_args.skipsetup:
        print(
            "Configuring a new order. If you'd like to continue uploading cards to an existing project,"
            "start this program with the -skipsetup option and follow the printed instructions."
            "example: ./autofill -skipsetup"
        )
        configure_order(driver)
    else:
        print(
            "Please sign in and select an existing project to continue editing."
            "Once you've signed in, return to the script execution window and press ENTER."
        )
        driver.get("https://www.makeplayingcards.com/login.aspx")
        raw_input("Press Enter to continue...")

    insert_card_fronts(bar, driver)

    # Page through to backs
    driver.execute_script("javascript:oDesign.setNextStep();")
    try:
        alert = driver.switch_to.alert
        alert.accept()
    except NoAlertPresentException:
        pass

    # Page over to the next step from "add text to fronts"
    wait(driver)
    try:
        driver.find_element_by_id("closeBtn").click()
    except NoSuchElementException:
        pass
    driver.execute_script("javascript:oDesign.setNextStep();")

    # Select "different images" for backs
    wait(driver)
    switch_to_frame(driver, "sysifm_loginFrame")

    if len(order.backs) == 0:
        # Same cardback for every card
        driver.execute_script("javascript:setMode('ImageText', 1);")
        driver.switch_to.default_content()

        # Pull the common cardback card info off the queue, then upload and insert it
        curr_card = q_cardback.get()
        if curr_card != ("", ""):
            pid = upload_card(driver, curr_card[0])
            insert_card(driver, pid, [0])
        bar.update(1)

    else:
        # Different cardbacks
        driver.execute_script("javascript:setMode('ImageText', 0);")
        driver.switch_to.default_content()

        # Insert specified cardbacks
        cards_with_backs = []
        for i in range(0, len(cardsinfo_back)):
            curr_card = q_back.get()
            if curr_card != ("", ""):
                pid = upload_card(driver, curr_card[0])
                insert_card(driver, pid, curr_card[1])

            # Keep track of the back slots we've filled
            cards_with_backs.extend(curr_card[1])
            bar.update(1)

        # Determine which slots require the common cardback
        # TODO: Is there a more efficient way to do this? Look at DOM instead?
        total_cards = order.details.quantity
        cards_needing_backs = [
            x for x in range(0, total_cards) if x not in cards_with_backs
        ]

        # Upload and insert the common cardback
        curr_card = q_cardback.get()
        if curr_card != ("", ""):
            pid = upload_card(driver, curr_card[0])
            insert_card(driver, pid, cards_needing_backs)
        bar.update(1)

    # Page through to finalise project
    driver.execute_script("javascript:oDesign.setNextStep();")
    try:
        alert = driver.switch_to.alert
        alert.accept()
    except NoAlertPresentException:
        pass
    wait(driver)
    time.sleep(1)
    driver.execute_script("javascript:oDesign.setNextStep();")

    # Page over to the next step from "add text to backs"
    wait(driver)
    driver.execute_script("javascript:oDesign.setNextStep();")


# Insert card fronts
def insert_card_fronts(bar, driver):
    for i in range(0, len(cardsinfo_front)):
        curr_card = q_front.get()
        slots = curr_card[1]
        filepath = curr_card[0]

        if curr_card != ("", "") and card_not_uploaded(driver, slots):
            pid = upload_card(driver, filepath)
            insert_card(driver, pid, slots)

        bar.update(1)


# Performs all of the preliminary order configuration that's needed before the card upload process can begin.
def configure_order(driver):
    # Load Custom Game Cards (63mm x 88mm) page
    driver.get("https://www.makeplayingcards.com/design/custom-blank-card.html")

    # Select card stock
    stock_dropdown = Select(driver.find_element_by_id("dro_paper_type"))
    stock_dropdown.select_by_visible_text(order.details.stock)

    # Select number of cards
    qty_dropdown = Select(driver.find_element_by_id("dro_choosesize"))
    qty_dropdown.select_by_value(order.details.bracket)

    # Switch the finish to foil if the user ordered foil cards
    if order.details.foil:
        foil_dropdown = Select(driver.find_element_by_id("dro_product_effect"))
        foil_dropdown.select_by_value("EF_055")

    # Accept current settings and move to next step
    driver.execute_script(
        "javascript:doPersonalize('https://www.makeplayingcards.com/products/pro_item_process_flow.aspx')"
    )

    # Set the desired number of cards, then move to the next step
    switch_to_frame(driver, "sysifm_loginFrame")
    driver.execute_script(
        "javascript:document.getElementById('txt_card_number').value="
        + str(order.details.quantity)
        + ";"
    )

    # Select "different images" for front
    driver.execute_script("javascript:setMode('ImageText', 0);")
    driver.switch_to.default_content()


def wait(driver):
    # Wait until the loading circle on MPC disappears before exiting from this function
    try:
        # Recently changed to <sysdiv_wait> from <sysimg_wait>, because sysimg_wait sometimes doesn't appear when
        # inserting the first card for an order, so only the first slot in the first image's slots would be filled
        wait_elem = driver.find_element_by_id("sysdiv_wait")
        # Wait for the element to become invisible
        while True:
            try:
                WebDriverWait(driver, 100).until(invisibility_of_element(wait_elem))
            except TimeoutException:
                continue
            break
    except NoSuchElementException:
        return


def download_card(bar: tqdm, cardinfo):
    card_item = ("", "")
    try:
        # Retrieve file ID and face from function argument
        file_id = cardinfo[0]
        file_face = cardinfo[3]
        # Attempt to retrieve the filename from function argument (XML)
        try:
            filename = cardinfo[2]
            # this is pretty fucking stupid but if it works it works
            if filename == "":
                raise IndexError

        except IndexError:
            # Can't retrieve filename from argument (XML) - retrieve it from a google app query instead
            # Credit to https://tanaikech.github.io/2017/03/20/download-files-without-authorization-from-google-drive/
            # use the results with a 'with' statement to avoid issues w/ connection broken
            try:
                with requests_post(
                    "https://script.google.com/macros/s/AKfycbw90rkocSdppkEuyVdsTuZNslrhd5zNT3XMgfucNMM1JjhLl-Q/exec",
                    data={"id": file_id},
                    timeout=30,
                ) as r_info:
                    filename = r_info.json()["name"]
            except requests_Timeout:
                # Failed to retrieve image name - add it to error queue
                print("cant get filename so gonna exih")
                q_error.put(
                    f"Failed to retrieve filename for image with ID {TEXT_BOLD}{file_id}{TEXT_END} >"
                )

        # in the case of file name request failing, filepath will be referenced before assignment unless we do this
        filepath = ""
        if filename:
            # Split the filename on extension and add in the ID as well
            # The filename with and without the ID in parentheses is checked for, so if the user downloads the image from
            # Google Drive without modifying the filename, it should work as expected
            # However, looking for the file with the ID in parentheses is preferred because it eliminates the possibility
            # of filename clashes between different images
            filename_split = filename.rsplit(".", 1)
            filename_id = filename

            # Filepath from filename
            # TODO: os.path.join?
            filepath = cards_folder + "/" + filename

            if not os.path.isfile(filepath) or os.path.getsize(filepath) <= 0:
                # The filepath without ID in parentheses doesn't exist - change the filepath to contain the ID instead
                filepath = cards_folder + "/" + filename_id

            # Download the image if it doesn't exist, or if it does exist but it's empty
            if (not os.path.isfile(filepath)) or os.path.getsize(filepath) <= 0:
                # Google script request for file contents
                # Set the request's timeout to 30 seconds, so if the server decides to not respond, we can
                # move on without stopping the whole autofill process    )) > 0 and text_to_list(cardinfo[1])[0] > 10:
                try:

                    # Five attempts at downloading the image, in case the api returns an empty image for whatever reason
                    attempt_counter = 0
                    image_downloaded = False
                    while attempt_counter < 5 and not image_downloaded:

                        with requests_post(
                            "https://script.google.com/macros/s/AKfycbzzCWc2x3tfQU1Zp45LB1P19FNZE-4njwzfKT5_Rx399h-5dELZWyvf/exec",
                            data={"id": file_id},
                            timeout=120,
                        ) as r_contents:

                            # Check if the response returned any data
                            filecontents = r_contents.json()["result"]
                            if len(filecontents) > 0:
                                # Download the image
                                f = open(filepath, "bw")
                                f.write(np_array(filecontents, dtype=np_uint8))
                                f.close()
                                image_downloaded = True
                            else:
                                attempt_counter += 1

                    if not image_downloaded:
                        # Tried to download image three times and never got any data, add to error queue
                        q_error.put(
                            f"{TEXT_BOLD}{filename}{TEXT_END}:\n  https://drive.google.com/uc?id={file_id}&export=download"
                        )

                except requests_Timeout:
                    # Failed to download image because of a timeout error - add it to error queue
                    q_error.put(
                        f"{TEXT_BOLD}{filename}{TEXT_END}:\n  https://drive.google.com/uc?id={file_id}&export=download"
                    )

        # Same check as before - if, after we've tried to download the image, the file doesn't exist or is empty,
        # or we couldn't retrieve the filename, we'll add it to an error queue and move on
        # We also decide on what to stick onto the queue here - error'd cards still go onto the queue to avoid
        # counting issues, but they're put on as empty strings so the main thread knows to skip them
        if os.path.isfile(filepath) and os.path.getsize(filepath) > 0 and filename:
            # Cards are normally put onto the queue as tuples of the image filepath and slots
            card_item = (filepath, text_to_list(cardinfo[1]))

    except Exception as e:
        # Really wanna put the nail in the coffin of stalling when an error occurs during image downloads
        # Any uncaught exceptions just get ignored and the card is skipped, adding the empty entry onto the appropriate queue
        # print("encountered an unexpected error <{}>".format(e))
        q_error.put(f"https://drive.google.com/uc?id={file_id}&export=download")

    # Add to the appropriate queue
    if file_face == "front":
        q_front.put(card_item)
    elif file_face == "back":
        q_back.put(card_item)
    elif file_face == "cardback":
        q_cardback.put(card_item)

    # Increment progress bar
    bar.update(1)


def upload_card(driver, filepath):
    if filepath != "" and os.path.isfile(filepath) and os.path.getsize(filepath) > 0:
        num_elems = len(driver.find_elements_by_xpath("//*[contains(@id, 'upload_')]"))

        # if an image is uploading already, wait for it to finish uploading before continuing
        progress_container = driver.find_element_by_id("divFileProgressContainer")

        while progress_container.value_of_css_property("display") != "none":
            time.sleep(3)

        while progress_container.value_of_css_property("display") == "none":
            # Attempt to upload card until the upload progress bar appears
            driver.find_element_by_xpath('//*[@id="uploadId"]').send_keys(filepath)
            time.sleep(1)
            progress_container = driver.find_element_by_id("divFileProgressContainer")

        # Wait as long as necessary for the image to finish uploading
        while True:
            try:
                # Wait until the image has finished uploading
                elem = driver.find_elements_by_xpath("//*[contains(@id, 'upload_')]")
                if len(elem) > num_elems:
                    # Return the uploaded card's PID so we can easily insert it into slots
                    return elem[-1].get_attribute("pid")

                time.sleep(2)

            except UnexpectedAlertPresentException:
                # If the user clicks on the window, alerts can pop up - we just want to dismiss these and move on
                try:
                    alert = driver.switch_to.alert
                    alert.accept()
                except NoAlertPresentException:
                    pass
    else:
        # Returns an empty string if the file does not exist
        q_error.put(
            f"Failed to upload image to MPC at path {TEXT_BOLD}{filepath}{TEXT_END}"
        )
        return ""


def card_not_uploaded(driver, slots):
    results = 0

    for slot in slots:
        xpath = "//*[contains(@src, 'default.gif') and @index={}]".format(slot)
        results += len(driver.find_elements_by_xpath(xpath))

    return len(slots) == results

def insert_card(driver, pid, slots):
    if pid != "":
        # Use mpc's JS functions to insert cards without simulated drag/drop
        driver.execute_script("javascript: l = PageLayout.prototype")
        for slot in slots:
            # Insert the card into each slot and wait for the page to load before continuing
            cmd = 'javascript:l.applyDragPhoto(l.getElement3("dnImg", {}), 0, "{}")'.format(
                slot, pid
            )
            driver.execute_script(cmd)
            wait(driver)


if __name__ == "__main__":
    print("MPC Autofill initialising.")
    t = time.time()

    # xml_glob = list(glob(currdir()+"*.xml"))
    xml_glob = list(glob(os.path.join(currdir(), "*.xml")))
    filename = ""
    if len(xml_glob) <= 0:
        input("No XML files found in this directory. Press enter to exit.")
        sys.exit(0)
    elif len(xml_glob) == 1:
        filename = xml_glob[0]
    else:
        # let user select XML file interactively
        xml_select_string = (
            "Multiple XML files found. Please select one for this order: "
        )
        if IS_WINDOWS:
            questions = [
                inquirer_List(
                    "xml_choice",
                    message=xml_select_string,
                    choices=xml_glob,
                    carousel=True,
                )
            ]
            filename = inquirer_prompt(questions)["xml_choice"]
        else:
            filename = enquiries_choose(xml_select_string, xml_glob)

    # parse xml
    tree = ET.parse(filename)
    root = tree.getroot()
    order = XML_Order(root)

    # print order details to user
    print(
        f"Successfully read XML file: {TEXT_BOLD}{filename}{TEXT_END}\n"
        f"Your order has a total of {TEXT_BOLD}{order.details.quantity}{TEXT_END} cards, in the MPC bracket of up to "
        f"{TEXT_BOLD}{order.details.bracket}{TEXT_END} cards.\n{TEXT_BOLD}{order.details.stock}{TEXT_END} cardstock "
        f"({TEXT_BOLD}{'foil' if order.details.foil else 'nonfoil'}{TEXT_END}).\n\n"
        f"Starting card downloader and webdriver processes."
    )

    # Extract information out of XML doc
    # Determine if this XML file is pre-3.0 (does not include search queries or filenames)
    if len(order.fronts[0]) > 2:
        # XML is 3.0-onwards, and filename can be retrieved
        cardsinfo_front = [(x.id, x.slots, x.name, "front") for x in order.fronts]
        cardsinfo_back = [(x.id, x.slots, x.name, "back") for x in order.backs]
    else:
        # XML is pre-3.0, and filename must be retrieved from google API request
        cardsinfo_front = [(x[0].text, x[1].text, "", "front") for x in order.fronts]
        cardsinfo_back = [(x[0].text, x[1].text, "", "back") for x in order.backs]

    cardsinfo_cardback = [(order.cardback.text, "", "", "cardback")]
    cardsinfo = cardsinfo_front + cardsinfo_back + cardsinfo_cardback

    # Set up chrome driver window here to avoid tqdm issues
    chrome_options = Options()
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    chrome_options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
    driver.set_window_size(1200, 900)
    driver.implicitly_wait(5)
    driver.set_network_conditions(offline=False, latency=5, throughput=5 * 125000)

    # Create ThreadPoolExecutor to download card images with, and progress bars for downloading and uploading
    with ThreadPoolExecutor(max_workers=5) as pool, tqdm(
        position=0, total=len(cardsinfo), desc="DL", leave=True
    ) as dl_progress, tqdm(
        position=1, total=len(cardsinfo), desc="UL", leave=False
    ) as ul_progress:
        # Download each card image in parallel, with the same progress bar input each time
        pool.map(partial(download_card, dl_progress), cardsinfo)
        # Launch the main webdriver automation function
        fill_cards(ul_progress, driver, root)
        dl_progress.close()
        ul_progress.close()

    print("\nAutofill complete!")

    # If any card images couldn't be downloaded, mention it here
    if not q_error.empty():
        print(
            "\nThe following card images couldn't be downloaded automatically. Sorry about that!\n"
            "Please download the images and insert them into your order manually.\n"
        )
        while not q_error.empty():
            print(q_error.get() + "\n")

    # Stopwatch for total autofill time
    t_total = time.time() - t
    hours = floor(t_total / 3600)
    mins = floor(t_total / 60) - hours * 60
    secs = int(t_total - (mins * 60) - (hours * 3600))

    print("Elapsed time: ", end="")
    if hours > 0:
        print("{} hours, ".format(hours), end="")
    print("{} minutes and {} seconds.".format(mins, secs))

    input(
        "Please review the order and ensure everything is correct before placing \n"
        "your order. If you need to make any changes to your order, you can do so \n"
        "by adding it to your Saved Projects.\n"
        "Continue with saving or purchasing your order in-browser, and press Enter here \n"
        "to finish up when you're done.\n"
    )
    sys.exit()
