from app.editor_app import App
import sys
import os

# Get the absolute path to the 'lib' folder
base_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(base_dir, "lib")

# Add to sys.path
sys.path.insert(0, lib_path)

if __name__ == "__main__":
    app = App()
    app.mainloop()
