import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import google.generativeai as genai
from threading import Thread
import sys
import time

USER_DATA_FILE = "user_data.json"

class ConsoleLogger:
    """Redirects console output (stdout and stderr) to the Text widget."""
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)  # Auto-scroll to the latest message

    def flush(self):
        pass  # Required for compatibility with some output streams

def save_user_data(data):
    """Save user data to a JSON file."""
    with open(USER_DATA_FILE, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def load_user_data():
    """Load user data from a JSON file."""
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    return {}

# GUI Application
def run_app():
    user_data = load_user_data()  # Load saved data if available

    def validate_inputs():
        """Validate user inputs in the form."""
        errors = []

        # Check required fields
        if not api_key_entry.get():
            errors.append("Gemini API Key is required.")
        if not spreadsheet_id_entry.get():
            errors.append("Spreadsheet ID is required.")
        if not sheet_name_entry.get():
            errors.append("Sheet Name is required.")
        if not creds_file_path.get():
            errors.append("Google Credentials File is required.")
        if not prompt_file_path.get():
            errors.append("Prompt File is required.")
        if not model_var.get():
            errors.append("Please select a Gemini model.")

        # Check Result Folder if the checkbox is selected
        if save_results_var.get() and not result_folder_entry.get():
            errors.append("Result Folder is required when saving results locally.")

        # Check column names (this will be validated later against the spreadsheet content)
        if not title_entry.get():
            errors.append("Title Column Name is required.")
        if not recipe_entry.get():
            errors.append("Recipe Column Name is required.")
        if not midjourney_entry.get():
            errors.append("Midjourney Prompt Column Name is required.")

        # Return a list of errors
        return errors

    def validate_columns(sheet, required_columns):
        """Check if required columns exist in the spreadsheet."""
        errors = []

        # Get the header row (assumes the first row contains column names)
        try:
            header = sheet.row_values(1)  # First row as header
        except Exception as e:
            raise Exception(f"Failed to fetch header row: {e}")

        # Check for missing columns
        for column in required_columns:
            if column not in header:
                errors.append(f"Missing column: {column}")

        return errors

    def save_inputs():
        """Save current inputs to the JSON file."""
        data = {
            "gemini_api_key": api_key_entry.get(),
            "spreadsheet_id": spreadsheet_id_entry.get(),
            "sheet_name": sheet_name_entry.get(),
            "title_entry": title_entry.get(),
            "recipe_entry": recipe_entry.get(),
            "midjourney_entry": midjourney_entry.get(),
            "creds_file": creds_file_path.get(),
            "prompt_file": prompt_file_path.get(),
            "selected_model": model_var.get(),
            "result_folder": result_folder_entry.get() if result_folder_entry is not None else "",
            "save_result_locally": save_results_var.get()
        }
        save_user_data(data)
        print("Settings saved!\n")

    def get_next_post_folder(result_folder):
        # Define the base directory
        base_dir = result_folder

        # Ensure the base directory exists
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        # Get the last Week folder
        week_folders = [folder for folder in os.listdir(base_dir) if folder.startswith("Week")]

        # Sort week folders by extracting the number after "Week"
        week_folders.sort(key=lambda x: int(x.split()[-1]))

        if week_folders:
            latest_week = week_folders[-1]
        else:
            latest_week = "Week 1"  # First week
            os.makedirs(os.path.join(base_dir, latest_week))

        # Get the last Day folder in the latest Week folder
        week_path = os.path.join(base_dir, latest_week)
        day_folders = [folder for folder in os.listdir(week_path) if folder.startswith("Day")]

        # Sort day folders by extracting the number after "Day"
        day_folders.sort(key=lambda x: int(x.split()[-1]))

        if day_folders:
            latest_day = day_folders[-1]
        else:
            latest_day = "Day 1"  # First day
            os.makedirs(os.path.join(week_path, latest_day))

        # Get the last Post folder in the latest Day folder
        day_path = os.path.join(week_path, latest_day)
        post_folders = [folder for folder in os.listdir(day_path) if folder.startswith("Post")]

        # Sort post folders by extracting the number after "Post"
        post_folders.sort(key=lambda x: int(x.split()[-1]))

        if post_folders:
            latest_post = post_folders[-1]
        else:
            latest_post = "Post 1"  # First post
            os.makedirs(os.path.join(day_path, latest_post))
            return os.path.join(day_path, latest_post)

        # Check if we need to create a new Post folder
        post_number = int(latest_post.split()[-1])

        if post_number >= 24:
            # If we reach 24 posts, create a new Day folder
            day_number = int(latest_day.split()[-1]) + 1

            if day_number > 7:
                # If we reach Day 7, create a new Week folder
                week_number = int(latest_week.split()[-1]) + 1
                latest_week = f"Week {week_number}"
                week_path = os.path.join(base_dir, latest_week)
                os.makedirs(week_path)
                latest_day = "Day 1"  # Reset to Day 1
                day_number = 1

            else:
                os.makedirs(os.path.join(week_path, f"Day {day_number}"))
                latest_day = f"Day {day_number}"

            day_path = os.path.join(week_path, latest_day)
            latest_post = "Post 1"
        else:
            post_number += 1
            latest_post = f"Post {post_number}"

        post_path = os.path.join(day_path, latest_post)
        os.makedirs(post_path)  # Create the new Post folder

        return post_path

    # Step 2: Generate ChatGPT completions
    def generate_completion(prompt, selected_model):
        try:
            print("---- gemini request started ----")

            model = genai.GenerativeModel(selected_model)
            response = model.generate_content(prompt)
            parsed_data = json.loads(response.text.replace('```json','').replace('```', ''))
            recipe = parsed_data["recipe"]
            midjourney_prompt = parsed_data["midjourney-prompt"]
            print("---- gemini response ----")
            return recipe, midjourney_prompt
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
        except Exception as e:
            print(f"Error generating completion: {e}")

        return '', ''  # Return empty strings in case of error

    def validate_sheet_name(client, spreadsheet_id, sheet_name):
        """Validate if the provided sheet name exists in the spreadsheet."""
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
            sheet_names = [sheet.title for sheet in spreadsheet.worksheets()]
            if sheet_name not in sheet_names:
                return f"Sheet name '{sheet_name}' does not exist in the spreadsheet."
            return None
        except gspread.exceptions.SpreadsheetNotFound:
            return "Spreadsheet not found or access denied."
        except Exception as e:
            return f"An unexpected error occurred while validating the sheet name: {e}"

    def validate_gemini_api_key(api_key):
        """Validate the Gemini API key by making a test request."""
        try:
            # Configure and test the Gemini API key
            genai.configure(api_key=api_key)
            genai.GenerativeModel("gemini-2.0-flash").generate_content("Test prompt")
            return None  # No error means the key is valid
        except Exception as e:
            return f"Invalid Gemini API key: {e}"

    def get_available_models(api_key):
        """Fetches the available Gemini models dynamically."""
        try:
            genai.configure(api_key=api_key)
            available_models = [model.name for model in genai.list_models() if 'generateContent' in model.supported_generation_methods]
            return available_models
        except Exception as e:
            print(f"Error fetching available models: {e}")
            return []

    # Function to start the main process with user-provided inputs
    def start_automation():
        def process():
            try:
                # Record the start time
                start_time = time.time()

                errors = validate_inputs()
                if errors:
                    messagebox.showerror("Validation Error", "\n".join(errors))
                    return

                # Get user inputs
                gemini_api_key = api_key_entry.get()
                spreadsheet_id = spreadsheet_id_entry.get()
                sheet_name = sheet_name_entry.get()
                creds_file = creds_file_path.get()
                prompt_file = prompt_file_path.get()
                result_folder = result_folder_entry.get() if result_folder_entry is not None else ""
                title = title_entry.get()
                recipe = recipe_entry.get()
                midjourney = midjourney_entry.get()
                selected_model = model_var.get()
                save_results = save_results_var.get()

                if not all([gemini_api_key, spreadsheet_id, sheet_name, creds_file, prompt_file, recipe, title, midjourney]):
                    messagebox.showerror("Input Error", "All fields are required!")
                    return
                save_inputs()
                print("--- Starting Automation ---\n")
                api_key_error = validate_gemini_api_key(gemini_api_key)
                if api_key_error:
                    messagebox.showerror("Gemini API Key Error", api_key_error)
                    return
                genai.configure(api_key=gemini_api_key)

                # Google Sheets API setup
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                credentials = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
                client = gspread.authorize(credentials)
                sheet_name_error = validate_sheet_name(client, spreadsheet_id, sheet_name)
                if sheet_name_error:
                    messagebox.showerror("Sheet Name Error", sheet_name_error)
                    return
                try:
                    sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
                except gspread.exceptions.SpreadsheetNotFound:
                    messagebox.showerror("Spreadsheet Error", "Spreadsheet not found or access denied.")
                    return

                # Define the path to the text file containing the prompt
                with open(prompt_file, 'r', encoding='utf-8') as file:
                    prompt_template = file.read()

                # Open the spreadsheet and worksheet
                sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
                print("Reading and filtering rows from the spreadsheet...")
                # Validate column names
                required_columns = [title, recipe, midjourney]
                column_errors = validate_columns(sheet, required_columns)
                if column_errors:
                    messagebox.showerror("Column Error", "\n".join(column_errors))
                    return
                # Step 1: Read and filter rows
                rows = sheet.get_all_records()
                filtered_rows = [
                    row for row in rows if not row[recipe] and not row[midjourney] and row[title]
                ]
                print(f"Found {len(filtered_rows)} rows to process.\n")
                
                # Initialize a counter for processed rows
                processed_count = 0

                for row_index, row in enumerate(rows, start=2):  # Start from 2 to match the sheet's row numbering
                    if row not in filtered_rows:
                        continue

                    # Increment the processed count
                    processed_count += 1

                    print(f"Processing row {processed_count} with title: {row[title]}")
                    # Step 4: Replace the {{Recipe}} placeholder with the value of row[title]
                    prompt = prompt_template.replace("{{Recipe}}", row[title])
                    try:
                        # Get the recipe and MidJourney prompt from the OpenAI response
                        recipe_result, midjourney_prompt = generate_completion(prompt, selected_model)

                        if recipe_result and midjourney_prompt:
                            sheet.update_cell(row_index, sheet.row_values(1).index(recipe) + 1, recipe_result)  # Column D is index 4 (for the recipe)
                            sheet.update_cell(row_index, sheet.row_values(1).index(midjourney) + 1, midjourney_prompt)  # Column E is index 5 (for MidJourney prompt)
                            print("--- recipe: "+row[title]+": written ---")

                            if save_results:
                                print("Save the recipe in a text file in the appropriate folder")
                                post_folder = get_next_post_folder(result_folder)
                                recipe_file_path = os.path.join(post_folder, "recipe.txt")
                                with open(recipe_file_path, 'w', encoding='utf-8') as file:
                                    file.write(recipe_result)

                        print(f"Row '{row[title]}' processed successfully.\n")
                    except Exception as e:
                        print(f"ERROR processing row {processed_count} with title '{row[title]}': {e}\n")
                # Record the end time
                end_time = time.time()
                # Calculate the elapsed time in seconds
                elapsed_time_seconds = end_time - start_time
                # Convert elapsed time to hours, minutes, and seconds
                hours = int(elapsed_time_seconds // 3600)
                minutes = int((elapsed_time_seconds % 3600) // 60)
                seconds = int(elapsed_time_seconds % 60)
                # Format the time as HH:MM:SS
                elapsed_time_str = f"{hours:02}:{minutes:02}:{seconds:02}"

                # Print the elapsed time in the console
                print(f"Time taken by script: {elapsed_time_str}")

                # Show completion message with the elapsed time
                messagebox.showinfo("Success", f"Automation completed successfully!\nTime taken: {elapsed_time_str}")
            except Exception as e:
                print("Error", f"An error occurred: {e}")
        Thread(target=process).start()

    # GUI Setup
    root = tk.Tk()
    root.title("Gouzak - Recipe Automation Tool")

    # Center the window (modified)
    def center_window(root):
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        # Calculate position, but add a safety margin
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)

        # Ensure the window isn't placed off-screen
        x = max(0, x)
        y = max(0, y)

        root.geometry(f"+{x}+{y}")

    root.after(1, lambda: center_window(root)) # Center after window is drawn

    # Labels and Entry Fields
    ttk.Label(root, text="Gemini API Key:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
    api_key_entry = ttk.Entry(root, width=50)
    api_key_entry.insert(0, user_data.get("gemini_api_key", ""))  # Pre-fill with saved data
    api_key_entry.grid(row=0, column=1, padx=10, pady=5)

    # Dynamically populate Gemini models
    available_models = []

    def update_models():
        nonlocal available_models
        api_key = api_key_entry.get()
        if api_key:
            available_models = get_available_models(api_key)
        else:
            available_models = ["Enter API Key First"]  # Placeholder if no API Key

        model_dropdown['values'] = available_models  # Update dropdown values

        # Set selected model, prioritizing saved value if available
        if user_data.get("selected_model") and user_data.get("selected_model") in available_models:
             model_var.set(user_data.get("selected_model"))
        elif available_models:
            model_var.set(available_models[0])  # Set default to the first available model if any
        else:
            model_var.set("No models found")  # Display message if no models available

    ttk.Label(root, text="Gemini Model:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
    model_var = tk.StringVar(value="")
    model_dropdown = ttk.Combobox(root, textvariable=model_var, state="readonly", width=47)
    model_dropdown.grid(row=1, column=1, padx=10, pady=5)

    # Initial population of model list
    update_models()

    # Trigger model list update when API key changes
    api_key_entry.bind("<FocusOut>", lambda event: update_models())
    api_key_entry.bind("<Return>", lambda event: update_models()) # Optional: Bind to Enter key

    ttk.Label(root, text="Spreadsheet ID:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
    spreadsheet_id_entry = ttk.Entry(root, width=50)
    spreadsheet_id_entry.insert(0, user_data.get("spreadsheet_id", ""))
    spreadsheet_id_entry.grid(row=2, column=1, padx=10, pady=5)

    ttk.Label(root, text="Sheet Name:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
    sheet_name_entry = ttk.Entry(root, width=50)
    sheet_name_entry.insert(0, user_data.get("sheet_name", ""))
    sheet_name_entry.grid(row=3, column=1, padx=10, pady=5)

    ttk.Label(root, text="Title Column Name:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
    title_entry = ttk.Entry(root, width=50)
    title_entry.insert(0, user_data.get("title_entry", ""))
    title_entry.grid(row=4, column=1, padx=10, pady=5)

    ttk.Label(root, text="Recipe Column Name:").grid(row=5, column=0, sticky="w", padx=10, pady=5)
    recipe_entry = ttk.Entry(root, width=50)
    recipe_entry.insert(0, user_data.get("recipe_entry", ""))
    recipe_entry.grid(row=5, column=1, padx=10, pady=5)

    ttk.Label(root, text="Image Prompt Column Name:").grid(row=6, column=0, sticky="w", padx=10, pady=5)
    midjourney_entry = ttk.Entry(root, width=50)
    midjourney_entry.insert(0, user_data.get("midjourney_entry", ""))
    midjourney_entry.grid(row=6, column=1, padx=10, pady=5)

    ttk.Label(root, text="Google Credentials File:").grid(row=7, column=0, sticky="w", padx=10, pady=5)
    creds_file_path = ttk.Entry(root, width=50)
    creds_file_path.grid(row=7, column=1, padx=10, pady=5)
    creds_file_path.insert(0, user_data.get("creds_file", ""))
    ttk.Button(root, text="Browse", command=lambda: _browse_file(creds_file_path)).grid(row=7, column=2, padx=10, pady=5)

    ttk.Label(root, text="Prompt File:").grid(row=8, column=0, sticky="w", padx=10, pady=5)
    prompt_file_path = ttk.Entry(root, width=50)
    prompt_file_path.insert(0, user_data.get("prompt_file", ""))
    prompt_file_path.grid(row=8, column=1, padx=10, pady=5)
    ttk.Button(root, text="Browse", command=lambda: _browse_file(prompt_file_path)).grid(row=8, column=2, padx=10, pady=5)

    # Checkbox for saving results locally
    save_results_var = tk.BooleanVar(value=user_data.get("save_result_locally") or False)  # Default is False
    save_results_checkbox = ttk.Checkbutton(
        root, text="Save Results Locally", variable=save_results_var
    )
    save_results_checkbox.grid(row=9, column=0, sticky="w", padx=10, pady=5)
    # Result Folder entry, only enabled if save_results_var is True

    def toggle_result_folder_fields(*args):
        global result_folder_label, result_folder_entry, result_folder_button

        if save_results_var.get():
            # Create fields if checkbox is checked
            if not result_folder_label:
                result_folder_label = ttk.Label(root, text="Result Folder:")
                result_folder_label.grid(row=10, column=0, sticky="w", padx=10, pady=5)

            if not result_folder_entry:
                result_folder_entry = ttk.Entry(root, width=50, state="normal")
                result_folder_entry.insert(0, user_data.get("result_folder", ""))
                result_folder_entry.grid(row=10, column=1, padx=10, pady=5)

            if not result_folder_button:
                result_folder_button = ttk.Button(
                    root,
                    text="Browse",
                    command=lambda: _browse_folder(result_folder_entry)
                )
                result_folder_button.grid(row=10, column=2, padx=10, pady=5)
        else:
            # Remove fields if checkbox is unchecked
            if result_folder_label:
                result_folder_label.grid_forget()
                result_folder_label = None

            if result_folder_entry:
                result_folder_entry.grid_forget()
                result_folder_entry = None

            if result_folder_button:
                result_folder_button.grid_forget()
                result_folder_button = None

    def _browse_file(entry_field):
        file_path = filedialog.askopenfilename()
        if file_path:
            entry_field.delete(0, tk.END)
            entry_field.insert(0, file_path)

    def _browse_folder(entry_field):
        folder_path = filedialog.askdirectory()
        if folder_path:
            entry_field.delete(0, tk.END)
            entry_field.insert(0, folder_path)

    toggle_result_folder_fields()
    save_results_var.trace_add("write", lambda *args: toggle_result_folder_fields())

    # Console Output
    ttk.Label(root, text="Console Output:").grid(row=11, column=0, sticky="nw", padx=10, pady=5)
    console_output = tk.Text(root, width=80, height=20, state="normal")
    console_output.grid(row=11, column=0, columnspan=3, padx=10, pady=5)

    # Redirect stdout to the console
    sys.stdout = ConsoleLogger(console_output)
    sys.stderr = ConsoleLogger(console_output)
    # Start Button
    # Frame to center the buttons
    button_frame = ttk.Frame(root)
    button_frame.grid(row=12, column=0, columnspan=3, pady=10)  # Frame spans 3 columns

    # Configure the columns in the parent grid to center-align the frame
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=1)
    root.grid_columnconfigure(2, weight=1)

    # Buttons within the frame
    save_button = ttk.Button(button_frame, text="Save Settings", command=save_inputs)
    save_button.pack(side="left", padx=5)  # Add small padding between buttons

    start_button = ttk.Button(button_frame, text="Start Automation", command=start_automation)
    start_button.pack(side="left", padx=5)  # Add small padding between buttons

    root.mainloop()

# Run the application
if __name__ == "__main__":
    result_folder_label = None
    result_folder_entry = None
    result_folder_button = None
    run_app()