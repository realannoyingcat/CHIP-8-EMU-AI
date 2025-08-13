# CATGPT 1.0 - CHIP-8 EMULATOR
# A complete, single-file CHIP-8 emulator with a ZSNES-inspired Tkinter GUI.
# To run: Save this code as a Python file (e.g., emulator.py) and run it.
# You will need CHIP-8 ROMs to load and play.

import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
import random
import time
import threading

class Chip8Emulator:
    """
    Encapsulates the entire CHIP-8 virtual machine and its GUI.
    """
    # --- Constants ---
    SCREEN_WIDTH = 64
    SCREEN_HEIGHT = 32
    PIXEL_SCALE = 12  # How large each CHIP-8 pixel appears on screen
    CLOCK_SPEED_HZ = 700  # Instructions per second
    TIMER_RATE_HZ = 60    # Rate at which delay and sound timers decrement

    # CHIP-8 has a 16-key hexadecimal keypad
    KEY_MAP = {
        '1': 0x1, '2': 0x2, '3': 0x3, '4': 0xC,
        'q': 0x4, 'w': 0x5, 'e': 0x6, 'r': 0xD,
        'a': 0x7, 's': 0x8, 'd': 0x9, 'f': 0xE,
        'z': 0xA, 'x': 0x0, 'c': 0xB, 'v': 0xF,
    }

    # Fontset for characters 0-F. Each character is 5 bytes long.
    FONTSET = [
        0xF0, 0x90, 0x90, 0x90, 0xF0,  # 0
        0x20, 0x60, 0x20, 0x20, 0x70,  # 1
        0xF0, 0x10, 0xF0, 0x80, 0xF0,  # 2
        0xF0, 0x10, 0xF0, 0x10, 0xF0,  # 3
        0x90, 0x90, 0xF0, 0x10, 0x10,  # 4
        0xF0, 0x80, 0xF0, 0x10, 0xF0,  # 5
        0xF0, 0x80, 0xF0, 0x90, 0xF0,  # 6
        0xF0, 0x10, 0x20, 0x40, 0x40,  # 7
        0xF0, 0x90, 0xF0, 0x90, 0xF0,  # 8
        0xF0, 0x90, 0xF0, 0x10, 0xF0,  # 9
        0xF0, 0x90, 0xF0, 0x90, 0x90,  # A
        0xE0, 0x90, 0xE0, 0x90, 0xE0,  # B
        0xF0, 0x80, 0x80, 0x80, 0xF0,  # C
        0xE0, 0x90, 0x90, 0x90, 0xE0,  # D
        0xF0, 0x80, 0xF0, 0x80, 0xF0,  # E
        0xF0, 0x80, 0xF0, 0x80, 0x80   # F
    ]

    def __init__(self, master):
        """
        Initializes the emulator's state and GUI.
        """
        self.master = master
        self.master.title("CATGPT CHIP-8 Emulator")
        
        # --- VM State ---
        self.memory = bytearray(4096)
        self.v = bytearray(16)  # 16 8-bit general purpose registers (V0-VF)
        self.i = 0              # 16-bit index register
        self.pc = 0x200         # Program counter starts at 0x200
        self.stack = []         # Stack for subroutines
        self.delay_timer = 0
        self.sound_timer = 0
        
        # Graphics buffer (64x32 monochrome)
        self.display_buffer = [0] * (self.SCREEN_WIDTH * self.SCREEN_HEIGHT)
        self.draw_flag = False

        # Input state
        self.keys = [0] * 16
        self.key_wait = -1 # Stores which V register to put the next keypress in, -1 if not waiting

        # --- Emulation Control ---
        self.running = False
        self.rom_loaded = False
        self.last_timer_update = 0
        self.last_cycle_update = 0

        self._load_fontset()
        self._setup_gui()
        
        # Start the main emulation thread
        self.emulation_thread = threading.Thread(target=self._emulation_loop, daemon=True)
        self.emulation_thread.start()
        
        # Start the GUI update loop
        self.master.after(16, self._update_gui) # ~60 FPS

    def _setup_gui(self):
        """Creates all the Tkinter widgets."""
        # ZSNES-like color scheme
        bg_color = '#2d2d39'
        fg_color = '#d0d0d0'
        canvas_bg = '#1a1a22'
        
        self.master.configure(bg=bg_color)
        
        # --- Menu Bar ---
        menu_bar = tk.Menu(self.master, bg=bg_color, fg=fg_color, tearoff=0)
        
        file_menu = tk.Menu(menu_bar, tearoff=0, bg=bg_color, fg=fg_color)
        file_menu.add_command(label="Open ROM...", command=self._load_rom)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.quit)
        menu_bar.add_cascade(label="File", menu=file_menu)

        emulation_menu = tk.Menu(menu_bar, tearoff=0, bg=bg_color, fg=fg_color)
        emulation_menu.add_command(label="Reset", command=self._reset)
        menu_bar.add_cascade(label="Emulation", menu=emulation_menu)
        
        help_menu = tk.Menu(menu_bar, tearoff=0, bg=bg_color, fg=fg_color)
        help_menu.add_command(label="About", command=self._show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.master.config(menu=menu_bar)

        # --- Canvas for Display ---
        canvas_width = self.SCREEN_WIDTH * self.PIXEL_SCALE
        canvas_height = self.SCREEN_HEIGHT * self.PIXEL_SCALE
        self.canvas = tk.Canvas(self.master, width=canvas_width, height=canvas_height, bg=canvas_bg, highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)

        # Create rectangle objects for each pixel to be updated later
        self.pixel_rects = []
        for y in range(self.SCREEN_HEIGHT):
            for x in range(self.SCREEN_WIDTH):
                x0 = x * self.PIXEL_SCALE
                y0 = y * self.PIXEL_SCALE
                x1 = x0 + self.PIXEL_SCALE
                y1 = y0 + self.PIXEL_SCALE
                rect = self.canvas.create_rectangle(x0, y0, x1, y1, fill=canvas_bg, outline="")
                self.pixel_rects.append(rect)

        # --- Keyboard Bindings ---
        self.master.bind("<KeyPress>", self._key_down)
        self.master.bind("<KeyRelease>", self._key_up)

    def _load_fontset(self):
        """Loads the built-in CHIP-8 fontset into memory."""
        for i, byte in enumerate(self.FONTSET):
            self.memory[i] = byte

    def _load_rom(self):
        """Opens a file dialog to load a ROM into memory."""
        filepath = filedialog.askopenfilename(
            title="Open CHIP-8 ROM",
            filetypes=(("CHIP-8 ROMs", "*.ch8;*.c8"), ("All files", "*.*"))
        )
        if not filepath:
            return

        try:
            with open(filepath, 'rb') as f:
                rom_data = f.read()
            
            self._reset() # Reset state before loading new ROM
            
            # Load ROM into memory starting at 0x200
            for i, byte in enumerate(rom_data):
                if 0x200 + i < len(self.memory):
                    self.memory[0x200 + i] = byte
                else:
                    raise IOError("ROM is too large for memory.")
            
            self.rom_loaded = True
            self.running = True
            self.master.title(f"CATGPT CHIP-8 Emulator - {filepath.split('/')[-1]}")

        except Exception as e:
            messagebox.showerror("Error Loading ROM", f"Failed to load the ROM file.\n\n{e}")
            self.running = False
            self.rom_loaded = False

    def _reset(self):
        """Resets the VM to its initial state."""
        self.v = bytearray(16)
        self.i = 0
        self.pc = 0x200
        self.stack = []
        self.delay_timer = 0
        self.sound_timer = 0
        self.keys = [0] * 16
        self.key_wait = -1
        
        # Clear display buffer and set draw flag to update the screen
        self.display_buffer = [0] * (self.SCREEN_WIDTH * self.SCREEN_HEIGHT)
        self.draw_flag = True

        # If a ROM was loaded, we can start running again
        self.running = self.rom_loaded

    def _key_down(self, event):
        key = event.keysym.lower()
        if key in self.KEY_MAP:
            chip8_key = self.KEY_MAP[key]
            self.keys[chip8_key] = 1
            # If we are waiting for a key press (opcode Fx0A)
            if self.key_wait != -1:
                self.v[self.key_wait] = chip8_key
                self.key_wait = -1
                self.running = True # Resume execution

    def _key_up(self, event):
        key = event.keysym.lower()
        if key in self.KEY_MAP:
            self.keys[self.KEY_MAP[key]] = 0

    def _show_about(self):
        messagebox.showinfo("About", "CATGPT CHIP-8 Emulator v1.0\n\nA single-file Python/Tkinter emulator.\n\nKeypad Mapping:\n1 2 3 4\nQ W E R\nA S D F\nZ X C V")
    
    def _update_gui(self):
        """Periodically checks if the screen needs redrawing."""
        if self.draw_flag:
            self._draw_screen()
            self.draw_flag = False
        self.master.after(16, self._update_gui) # Schedule next update

    def _draw_screen(self):
        """Updates the Tkinter canvas based on the display buffer."""
        on_color = '#e0e0ff'
        off_color = self.canvas.cget('bg')
        for i, pixel in enumerate(self.display_buffer):
            color = on_color if pixel else off_color
            self.canvas.itemconfig(self.pixel_rects[i], fill=color)

    def _emulation_loop(self):
        """The main loop running in a separate thread to not block the GUI."""
        cycle_interval = 1.0 / self.CLOCK_SPEED_HZ
        timer_interval = 1.0 / self.TIMER_RATE_HZ
        
        while True:
            if self.running:
                current_time = time.perf_counter()

                # --- Execute CPU Cycles ---
                if current_time - self.last_cycle_update > cycle_interval:
                    self._execute_cycle()
                    self.last_cycle_update = current_time

                # --- Update Timers ---
                if current_time - self.last_timer_update > timer_interval:
                    if self.delay_timer > 0:
                        self.delay_timer -= 1
                    if self.sound_timer > 0:
                        self.sound_timer -= 1
                        if self.sound_timer == 0:
                            # In a real implementation, you'd play a sound.
                            # For simplicity, we print to the console.
                            print("BEEP!")
                    self.last_timer_update = current_time
            else:
                # Sleep when not running to reduce CPU usage
                time.sleep(0.01)

    def _execute_cycle(self):
        """Fetches, decodes, and executes a single CHIP-8 opcode."""
        # Fetch opcode (2 bytes)
        opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        self.pc += 2

        # Decode and execute
        x = (opcode & 0x0F00) >> 8
        y = (opcode & 0x00F0) >> 4
        n = opcode & 0x000F
        kk = opcode & 0x00FF
        nnn = opcode & 0x0FFF

        # --- Opcode Implementations ---
        op_type = opcode & 0xF000

        if op_type == 0x0000:
            if opcode == 0x00E0:  # 00E0: CLS - Clear the display
                self.display_buffer = [0] * (self.SCREEN_WIDTH * self.SCREEN_HEIGHT)
                self.draw_flag = True
            elif opcode == 0x00EE:  # 00EE: RET - Return from a subroutine
                if self.stack:
                    self.pc = self.stack.pop()

        elif op_type == 0x1000:  # 1nnn: JP addr - Jump to location nnn
            self.pc = nnn

        elif op_type == 0x2000:  # 2nnn: CALL addr - Call subroutine at nnn
            self.stack.append(self.pc)
            self.pc = nnn

        elif op_type == 0x3000:  # 3xkk: SE Vx, byte - Skip next if Vx == kk
            if self.v[x] == kk:
                self.pc += 2

        elif op_type == 0x4000:  # 4xkk: SNE Vx, byte - Skip next if Vx != kk
            if self.v[x] != kk:
                self.pc += 2

        elif op_type == 0x5000:  # 5xy0: SE Vx, Vy - Skip next if Vx == Vy
            if self.v[x] == self.v[y]:
                self.pc += 2

        elif op_type == 0x6000:  # 6xkk: LD Vx, byte - Set Vx = kk
            self.v[x] = kk

        elif op_type == 0x7000:  # 7xkk: ADD Vx, byte - Set Vx = Vx + kk
            self.v[x] = (self.v[x] + kk) & 0xFF

        elif op_type == 0x8000:
            op_subtype = opcode & 0x000F
            if op_subtype == 0x0:    # 8xy0: LD Vx, Vy
                self.v[x] = self.v[y]
            elif op_subtype == 0x1:  # 8xy1: OR Vx, Vy
                self.v[x] |= self.v[y]
            elif op_subtype == 0x2:  # 8xy2: AND Vx, Vy
                self.v[x] &= self.v[y]
            elif op_subtype == 0x3:  # 8xy3: XOR Vx, Vy
                self.v[x] ^= self.v[y]
            elif op_subtype == 0x4:  # 8xy4: ADD Vx, Vy
                result = self.v[x] + self.v[y]
                self.v[0xF] = 1 if result > 255 else 0
                self.v[x] = result & 0xFF
            elif op_subtype == 0x5:  # 8xy5: SUB Vx, Vy
                self.v[0xF] = 1 if self.v[x] > self.v[y] else 0
                self.v[x] = (self.v[x] - self.v[y]) & 0xFF
            elif op_subtype == 0x6:  # 8xy6: SHR Vx {, Vy}
                self.v[0xF] = self.v[x] & 0x1
                self.v[x] >>= 1
            elif op_subtype == 0x7:  # 8xy7: SUBN Vx, Vy
                self.v[0xF] = 1 if self.v[y] > self.v[x] else 0
                self.v[x] = (self.v[y] - self.v[x]) & 0xFF
            elif op_subtype == 0xE:  # 8xyE: SHL Vx {, Vy}
                self.v[0xF] = (self.v[x] & 0x80) >> 7
                self.v[x] = (self.v[x] << 1) & 0xFF

        elif op_type == 0x9000:  # 9xy0: SNE Vx, Vy - Skip next if Vx != Vy
            if self.v[x] != self.v[y]:
                self.pc += 2

        elif op_type == 0xA000:  # Annn: LD I, addr - Set I = nnn
            self.i = nnn

        elif op_type == 0xB000:  # Bnnn: JP V0, addr - Jump to nnn + V0
            self.pc = nnn + self.v[0]

        elif op_type == 0xC000:  # Cxkk: RND Vx, byte - Set Vx = random & kk
            self.v[x] = random.randint(0, 255) & kk

        elif op_type == 0xD000:  # Dxyn: DRW Vx, Vy, nibble
            self.v[0xF] = 0
            start_x = self.v[x] % self.SCREEN_WIDTH
            start_y = self.v[y] % self.SCREEN_HEIGHT
            
            for row in range(n):
                sprite_byte = self.memory[self.i + row]
                pixel_y = start_y + row
                if pixel_y >= self.SCREEN_HEIGHT:
                    continue

                for col in range(8):
                    pixel_x = start_x + col
                    if pixel_x >= self.SCREEN_WIDTH:
                        continue
                    
                    # Check if the sprite pixel is on
                    if (sprite_byte & (0x80 >> col)) != 0:
                        index = pixel_x + (pixel_y * self.SCREEN_WIDTH)
                        # If drawing causes a pixel to be erased, set VF to 1
                        if self.display_buffer[index] == 1:
                            self.v[0xF] = 1
                        # XOR the pixel onto the display buffer
                        self.display_buffer[index] ^= 1
            
            self.draw_flag = True

        elif op_type == 0xE000:
            op_subtype = opcode & 0x00FF
            if op_subtype == 0x9E:  # Ex9E: SKP Vx - Skip next if key Vx is pressed
                if self.keys[self.v[x]] == 1:
                    self.pc += 2
            elif op_subtype == 0xA1:  # ExA1: SKNP Vx - Skip next if key Vx not pressed
                if self.keys[self.v[x]] == 0:
                    self.pc += 2

        elif op_type == 0xF000:
            op_subtype = opcode & 0x00FF
            if op_subtype == 0x07:   # Fx07: LD Vx, DT
                self.v[x] = self.delay_timer
            elif op_subtype == 0x0A: # Fx0A: LD Vx, K - Wait for key press
                self.key_wait = x
                self.running = False # Pause execution until key is pressed
            elif op_subtype == 0x15: # Fx15: LD DT, Vx
                self.delay_timer = self.v[x]
            elif op_subtype == 0x18: # Fx18: LD ST, Vx
                self.sound_timer = self.v[x]
            elif op_subtype == 0x1E: # Fx1E: ADD I, Vx
                self.i += self.v[x]
            elif op_subtype == 0x29: # Fx29: LD F, Vx - Set I to location of sprite for digit Vx
                self.i = self.v[x] * 5
            elif op_subtype == 0x33: # Fx33: LD B, Vx - Store BCD of Vx
                val = self.v[x]
                self.memory[self.i] = val // 100
                self.memory[self.i + 1] = (val % 100) // 10
                self.memory[self.i + 2] = val % 10
            elif op_subtype == 0x55: # Fx55: LD [I], Vx - Store registers V0 to Vx
                for j in range(x + 1):
                    self.memory[self.i + j] = self.v[j]
            elif op_subtype == 0x65: # Fx65: LD Vx, [I] - Read registers V0 to Vx
                for j in range(x + 1):
                    self.v[j] = self.memory[self.i + j]

if __name__ == "__main__":
    root = tk.Tk()
    emulator = Chip8Emulator(root)
    root.mainloop()

