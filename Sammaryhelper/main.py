from Sammaryhelper.gui import TelegramSummarizerGUI
import tkinter as tk

if __name__ == "__main__":
    root = tk.Tk()
    app = TelegramSummarizerGUI(root)
    
    def on_closing():
        app.root.quit()
        app.root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    app.run()
