import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import fitz # PDF
import math
import os
import tempfile
import tkinterDnD

HANDLE_SIZE = 5  # Размер квадратиков для изменения размера
MIN_SIZE_FACTOR = 0.2    # Минимальное уменьшение изображения (x5)
MAX_SIZE_FACTOR = 2

class CanvasCoordinateSystem:
    def __init__(self, canvas):
        self.canvas = canvas
        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0  # Масштабирование (мировые единицы -> пиксели)

    def update_transform(self, offset_x, offset_y, scale):
        """Обновляет параметры трансформации"""
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.scale = scale

    def world_to_screen(self, x, y):
        """Преобразует мировую точку в экранные координаты"""
        screen_x = self.canvas.winfo_width() / 2 + x * self.scale + self.offset_x
        screen_y = self.canvas.winfo_height() / 2 - y * self.scale + self.offset_y
        return screen_x, screen_y
    
    def screen_to_world(self, x,y):
        screen_x = self.canvas.winfo_width() / 2 - x / self.scale - self.offset_x
        screen_y = self.canvas.winfo_height() / 2 - y / self.scale - self.offset_y
        return -screen_x, screen_y

    def draw_axes(self):
        """Рисует оси X и Y"""
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        # Ось X
        self.canvas.create_line(0, height // 2 + self.offset_y,
                                width, height // 2 + self.offset_y,
                                fill="gray", dash=(4, 4))
        # Ось Y
        self.canvas.create_line(width // 2 + self.offset_x, 0,
                                width // 2 + self.offset_x, height,
                                fill="gray", dash=(4, 4))

        # Разметка осей
        step = 50  # шаг разметки в мировых координатах
        for i in range(-width//2, width//2, int(step * self.scale)):
            wx = i / self.scale
            sx = width // 2 + i + self.offset_x
            self.canvas.create_line(sx, height//2 - 5, sx, height//2 + 5, fill="black")
            if abs(wx) > 1e-6:
                self.canvas.create_text(sx, height//2 + 10, text=f"{wx:.0f}", fill="black")

        for i in range(-height//2, height//2, int(step * self.scale)):
            wy = -i / self.scale
            sy = height // 2 + i + self.offset_y
            self.canvas.create_line(width//2 - 5, sy, width//2 + 5, sy, fill="black")
            if abs(wy) > 1e-6:
                self.canvas.create_text(width//2 + 10, sy, text=f"{wy:.0f}", fill="black")

class ImageEditor:
    def __init__(self, root : tkinterDnD.Tk):
        ##############
        ### MARKUP ###
        ##############
        self.root = root
        self.root.title("PDF + ECP")
        self.root.geometry("1000x600")
        # self.stringvar = tk.StringVar()
        # self.stringvar.set('Drop here or drag from here!')

        # Canvas
        global_frame = tk.Frame(root)
        global_frame.pack(expand=True, fill=tk.BOTH)
        canvas_frame = tk.Frame(global_frame)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="gray")
        self.h_scroll = tk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.v_scroll = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.h_scroll.grid(row=1, column=0, sticky="ew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")

        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        # Controls Panel
        control_frame = tk.Frame(global_frame, width=300)
        control_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.info_label = tk.Label(control_frame, text="Информация о изображении", justify=tk.LEFT, anchor='nw', padx=5, pady=5)
        self.info_label.pack(fill=tk.X)

        btn_frame = tk.Frame(control_frame)
        btn_frame.pack(fill=tk.X)

        self.load_pdf_btn = tk.Button(btn_frame, text="Загрузить PDF", command=self.load_pdf)
        self.load_pdf_btn.pack(pady=5, padx=20, fill=tk.X)

        self.load_btn = tk.Button(btn_frame, text="Загрузить изображение", command=self.load_image)
        self.load_btn.pack(pady=5, padx=20, fill=tk.X)

        self.save_btn = tk.Button(btn_frame, text="Сохранить изображение", command=self.save_image, state=tk.DISABLED)
        self.save_btn.pack(pady=5, padx=20, fill=tk.X)

        self.print_btn = tk.Button(btn_frame, text="Печать", command=self.print_pdf, state=tk.DISABLED)
        self.print_btn.pack(pady=5, padx=20, fill=tk.X)

        page_frame = tk.Frame(control_frame)
        page_frame.pack(pady=10)
        
        self.page_frame_label = tk.Label(page_frame,text="Страница", justify=tk.CENTER, anchor="center")
        self.page_frame_label.pack(fill=tk.X)

        self.prev_page_btn = tk.Button(page_frame, text="◄",state=tk.DISABLED,command=self.page_prev)
        self.prev_page_btn.pack(side=tk.LEFT)

        self.page_input = tk.Entry(page_frame,state=tk.DISABLED,width=5)
        self.page_input.pack(side=tk.LEFT)

        self.next_page_btn = tk.Button(page_frame, text="►",state=tk.DISABLED,command=self.page_next)
        self.next_page_btn.pack(side=tk.LEFT)

        img_frame = tk.Frame(control_frame)
        img_frame.pack(pady=10)
        
        # self.img_left_btn = tk.Button(img_frame, text="←", command=self.img_left)
        # self.img_left_btn.pack(side=tk.LEFT)
        # self.img_up_btn = tk.Button(img_frame, text="↑", command=self.img_up)
        # self.img_up_btn.pack(side=tk.LEFT)
        # self.img_down_btn = tk.Button(img_frame, text="↓", command=self.img_down)
        # self.img_down_btn.pack(side=tk.LEFT)
        # self.img_right_btn = tk.Button(img_frame, text="→", command=self.img_right)
        # self.img_right_btn.pack(side=tk.LEFT)

        # Zooming
        self.zoom_frame = tk.Frame(control_frame)
        self.zoom_frame.pack(side=tk.BOTTOM, pady=15)

        self.zoom_in_btn = tk.Button(self.zoom_frame, text="Увеличить", command=self.zoom_in)
        self.zoom_in_btn.pack(side=tk.LEFT, padx=2)

        self.zoom_info = tk.Label(self.zoom_frame, text="100%", justify=tk.CENTER, anchor="center", padx=5,pady=5,width=4)
        self.zoom_info.pack(side=tk.LEFT)

        self.zoom_out_btn = tk.Button(self.zoom_frame, text="Уменьшить", command=self.zoom_out)
        self.zoom_out_btn.pack(side=tk.LEFT, padx=2)

        self.coord_system = CanvasCoordinateSystem(self.canvas)
        self.translation = [0, 0]  # Смещение мира относительно экрана
        self.zoom_level = 1.0      # Текущий уровень масштабирования

        #############
        ### LOGIC ###
        #############
        
        # Images
        self.__image = None # вставленное изображение
        self.__image_original_size = None
        self.world_image_pos = [0,0]
        self.__image_pos = [0,0]
        self.__drag_data = {"x": 0, "y": 0, "dragging": False, "mode": None}

        self.__pdf_doc: fitz.Document = None # полный pdf файл
        self.__pdf_page: fitz.Page = None # pdf страница
        #self.__current_page = None # какая страница 
        self.__pdf_image = None # вставленное изображение pdf
        self.__pdf_pos = [0,0] # Позиция pdf
        
        # Scaling
        self.__global_scale = 1 # масштаб отображения для вrсего
        self.__image_scale = 1 # логический масштаб картинки
        #self.computed_image_scale - масштаб отображения картинки для отображения
        
        # Event bindings
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Alt-MouseWheel>", self.on_mousewheel_alt)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self.on_mousewheel_ctrl)
        
        #dnd
        
        global_frame.register_drop_target("*")
        global_frame.bind("<<Drop>>", self.drop)
        global_frame.register_drag_source("*")
        global_frame.bind("<<DragInitCmd>>", self.drag_command)

    
    def drop(self,event : tkinterDnD.dnd.DnDEvent):
    # This function is called, when stuff is dropped into a widget
        #self.stringvar.set(event.data)
        files = self.root.tk.splitlist(event.data)
        pdf_path = None
        image_path = None
        wrong_paths = []

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext == ".pdf":
                pdf_path = file
            elif ext in [".png", ".jpg", ".jpeg", ".bmp"]:
                image_path = file
            else:
                wrong_paths.append(file)
        try:
            # Логика обработки
            if len(files) == 1:
                if pdf_path:
                    self.load_pdf_from_path(pdf_path)
                elif image_path:
                    self.load_image_from_path(image_path)
            elif len(files) >= 2:
                # Попробуем найти PDF и изображение
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext == ".pdf" and not pdf_path:
                        pdf_path = file
                    elif ext in [".png", ".jpg", ".jpeg", ".bmp"] and not image_path:
                        image_path = file

                if pdf_path and image_path:
                    self.load_pdf_from_path(pdf_path)
                    self.load_image_from_path(image_path)
                else:
                    if (len(wrong_paths) != 0):
                        messagebox.showwarning("Файлы", f"Некорректный(ые) файл(ы):\n\n{'\n'.join(wrong_paths)}")
                    else:
                        messagebox.showwarning("Файлы", f"Перенесите 1 pdf файл и 1 изображение.")
            else:
                messagebox.showwarning("Файлы", "Неподдерживаемый тип файла.")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать файл: {e}")
    
    def drag_command(self, event : tkinterDnD.dnd.DnDEvent):
    # This function is called at the start of the drag,
    # it returns the drag type, the content type, and the actual content
        return (tkinterDnD.COPY, "DND_Text", "Some nice dropped text!")

    @property
    def pdf_page(self):
        return self.__pdf_page

    @pdf_page.setter
    def pdf_page(self, page:fitz.Page):
        self.__pdf_page = page
        pix = self.pdf_page.get_pixmap(matrix=fitz.Matrix(2, 2))  # увеличенное качество
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.pdf_image = img
        self.auto_fit_scale()
        self.page_frame_label.config(text=f"Страница {page.number+1}/{self.pdf_doc.page_count}")
        self.save_btn.config(state=tk.NORMAL)
        self.print_btn.config(state=tk.NORMAL)
        self.prev_page_btn.config(state=tk.NORMAL)
        self.next_page_btn.config(state=tk.NORMAL)

    @property
    def pdf_doc(self):
        return self.__pdf_doc
    @pdf_doc.setter
    def pdf_doc(self, doc):
        self.__pdf_doc = doc
        self.pdf_page = self.pdf_doc.load_page(self.pdf_doc.page_count-1) # загрузка первой страницы

    @property
    def page(self):
        return self.pdf_page.number
    @page.setter
    def page(self, num):
        if self.pdf_doc.page_count == 1:
            return
        #if num >= self.pdf_doc.page_count or num < 0:
        #    print("error in setting page: number was too high")
        #    return
        self.pdf_page = self.pdf_doc.load_page(num % self.pdf_doc.page_count)

    @property
    def pdf_image(self):
        return self.__pdf_image
    @pdf_image.setter
    def pdf_image(self, img :Image.Image):
        self.__pdf_image = img
        self.canvas.yview_moveto(0)
        self.canvas.xview_moveto(0)
        self.update_canvas()

    @property
    def pdf_pos(self):
        return self.__pdf_pos
    @pdf_pos.setter
    def pdf_pos(self, pos):
        self.__pdf_pos = pos
        self.update_canvas()

    @property
    def image(self):
        return self.__image
    @image.setter
    def image(self, img :Image.Image):
        self.__image = img

    @property
    def computed_image_scale(self):
        return self.global_scale * self.image_scale
    
    @property
    def global_scale(self):
        return self.__global_scale
    @global_scale.setter
    def global_scale(self, num):
        self.__global_scale = num
        if (self.global_scale < MIN_SIZE_FACTOR):
            self.__global_scale = MIN_SIZE_FACTOR
        if (self.global_scale > MAX_SIZE_FACTOR):
            self.__global_scale = MAX_SIZE_FACTOR
        self.zoom_info.config(text=f"{math.floor(self.global_scale * 100)}%")
        self.update_canvas()

    @property
    def image_scale(self):
        return self.__image_scale
    @image_scale.setter
    def image_scale(self, num):
        self.__image_scale = num
        if (self.image_scale < MIN_SIZE_FACTOR):
            self.__image_scale = MIN_SIZE_FACTOR
        if (self.image_scale > MAX_SIZE_FACTOR):
            self.__image_scale = MAX_SIZE_FACTOR
        #self.update_canvas()

    @property
    def image_pos(self):
        return self.__image_pos
    @image_pos.setter
    def image_pos(self,pos):
        self.__image_pos = pos
        self.update_canvas()

    @property
    def image_original_size(self):
        return self.__image_original_size
    
    @image_original_size.setter
    def image_original_size(self,size):
        self.__image_original_size = size
    
    @property
    def drag_data(self):
        return self.__drag_data
    @drag_data.setter
    def drag_data(self,data):
        self.__drag_data = data
    
    def load_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if not path:
            return
        try:
            self.pdf_doc = fitz.open(path) # загрузка документа
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить PDF: {e}")

    def load_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
        if not path:
            return
        try:
            self.image = Image.open(path)
            #self.image = self.image.convert("RGBA")
            self.image_original_size = self.image.size
            self.image_pos = [0, 0]
            self.image_scale = 1
            #self.update_canvas()
            self.save_btn.config(state=tk.NORMAL)
            self.show_info()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить изображение:\n{e}")

    def save_image(self):
        from reportlab.pdfgen import canvas
        #from reportlab.lib.pagesizes import letter
        if not self.pdf_doc and not self.image:
            messagebox.showwarning("Предупреждение", "Нет PDF или изображения для сохранения.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                filetypes=[("PDF файлы", "*.pdf")])
        if not file_path:
            return

        try:
            # Создаем временную копию документа
            temp_doc = fitz.open()
            temp_doc.insert_pdf(self.pdf_doc)

            # Получаем текущую страницу
            page_num = self.page
            pdf_page = temp_doc.load_page(page_num)

            # Конвертируем позицию изображения в координаты PDF
            img_w, img_h = self.image.size
            scale = self.computed_image_scale / self.global_scale  # Учитываем масштабирование

            resized_img_w = img_w * scale
            resized_img_h = img_h * scale
            #world_pos_x, world_pos_y = self.image_pos
            world_pos_x = (self.image_pos[0] + (self.pdf_image.width - resized_img_w)/2)/2
            world_pos_y = (-self.image_pos[1] + (self.pdf_image.height - resized_img_h)/2)/2

            # world_pos_x -= resized_img_w / 2
            # world_pos_y -= resized_img_h / 2

            # Центр изображения в координатах PDF
            # rect = fitz.Rect(world_pos_x + resized_img_w / 2,
            #                 world_pos_y + resized_img_h / 2,
            #                 world_pos_x + resized_img_w,
            #                 world_pos_y + resized_img_h)
            rect = fitz.Rect(world_pos_x,
                             world_pos_y,
                             world_pos_x + resized_img_w / 2,
                             world_pos_y + resized_img_h / 2)

            # Сохраняем изображение во временный байт-поток
            import io
            img_data = io.BytesIO()
            self.image.save(img_data, format=self.image.format)
            
            # Вставляем изображение на страницу
            pdf_page.insert_image(rect, stream=img_data.getvalue())

            # Сохраняем результат
            temp_doc.save(file_path)
            temp_doc.close()

            messagebox.showinfo("Сохранение", "Файл успешно сохранён как PDF с наложенным изображением!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл: {e}")

    def print_pdf(self):
        if not self.pdf_doc and not self.image:
            messagebox.showwarning("Предупреждение", "Нет PDF или изображения для печати.")
            return

        try:
            # Создаем временный документ
            temp_doc = fitz.open()
            temp_doc.insert_pdf(self.pdf_doc)
            page_num = self.page
            pdf_page = temp_doc.load_page(page_num)

            # Подготовка изображения для вставки
            img_w, img_h = self.image.size
            scale = self.computed_image_scale / self.global_scale  # Учитываем масштабирование
            resized_img_w = img_w * scale
            resized_img_h = img_h * scale

            world_pos_x = (self.image_pos[0] + (self.pdf_image.width - resized_img_w)/2) / 2
            world_pos_y = (-self.image_pos[1] + (self.pdf_image.height - resized_img_h)/2) / 2

            rect = fitz.Rect(world_pos_x,
                            world_pos_y,
                            world_pos_x + resized_img_w / 2,
                            world_pos_y + resized_img_h / 2)

            # Сохраняем изображение во временный байт-поток
            import io
            img_data = io.BytesIO()
            self.image.save(img_data, format=self.image.format)

            # Вставляем изображение на страницу
            pdf_page.insert_image(rect, stream=img_data.getvalue())

            # Сохраняем временный PDF
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmpfile:
                temp_path = tmpfile.name
            temp_doc.save(temp_path)
            temp_doc.close()

            # Вызываем системную печать
            if os.name == 'nt':  # Windows
                os.startfile(temp_path)
            elif os.name == 'posix':  # Linux/macOS (может потребовать настройки)
                import subprocess
                subprocess.Popen(["lp", temp_path])
            else:
                messagebox.showinfo("Печать", "Печать не поддерживается на вашей платформе.")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подготовить файл для печати: {e}")

    def zoom_in(self):
        self.global_scale *= 1.10

    def zoom_out(self):
        self.global_scale /= 1.10

    def page_prev(self):
        self.page -= 1

    def page_next(self):
        self.page += 1

    def auto_fit_scale(self):
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if not self.pdf_image:
            return

        pdf_width, pdf_height = self.pdf_image.size

        scale_w = canvas_width / pdf_width
        scale_h = canvas_height / pdf_height
        new_scale = min(scale_w, scale_h)

        # Применяем ограничения
        new_scale = max(new_scale, MIN_SIZE_FACTOR)

        self.global_scale = new_scale


    def update_canvas(self):
        self.canvas.delete("all")
        
        
        #win_w, win_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.coord_system.update_transform(
            offset_x=self.translation[0],
            offset_y=self.translation[1],
            scale=self.global_scale
        )
        #self.coord_system.draw_axes()
        # Центр в мировых координатах
        #world_center_x = 0
        #world_center_y = 0

        screen_x, screen_y = self.coord_system.world_to_screen(0,0)

        if self.pdf_image:
            pdf_w, pdf_h = self.pdf_image.size
            scaled_pdf_size = (
                int(pdf_w * self.global_scale),
                int(pdf_h * self.global_scale)
            )
            scaled_pdf = self.pdf_image.resize(scaled_pdf_size, Image.Resampling.LANCZOS)
            self.tk_pdf_image = ImageTk.PhotoImage(scaled_pdf)

            pdf_anchor_x = screen_x - scaled_pdf.width / 2
            pdf_anchor_y = screen_y - scaled_pdf.height / 2

            self.canvas.create_image(pdf_anchor_x, pdf_anchor_y, image=self.tk_pdf_image, anchor=tk.NW, tags="pdf")

            #self.canvas.create_image(self.pdf_pos[0], self.pdf_pos[1], image=self.tk_pdf_image, anchor=tk.NW, tags="pdf")
        
        if self.image:
            w, h = self.image.size
            resized = self.image.resize((int(w * self.computed_image_scale), int(h * self.computed_image_scale)), Image.Resampling.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(resized)

            #img_x, img_y = self.coord_system.world_to_screen(self.image_pos[0],self.image_pos[1])

            wx, wy = self.image_pos
            img_screen_x, img_screen_y = self.coord_system.world_to_screen(wx, wy)
            img_anchor_x = img_screen_x - resized.width / 2
            img_anchor_y = img_screen_y - resized.height / 2

            #img_anchor_x = screen_x - resized.width / 2 + self.image_pos[0]
            #img_anchor_y = screen_y - resized.height / 2 + self.image_pos[1]

            self.image_id = self.canvas.create_image(img_anchor_x, img_anchor_y, image=self.tk_image, anchor=tk.NW, tags="image")

            # Рисуем только угловые ручки
            self.draw_corner_handles(img_anchor_x,img_anchor_y)

        bbox = self.canvas.bbox(tk.ALL)
        if bbox:
            self.canvas.configure(scrollregion=bbox)
    
    def draw_corner_handles(self,x,y):
        #x, y = self.image_pos
        w, h = self.image.size
        sw, sh = int(w * self.computed_image_scale), int(h * self.computed_image_scale)

        positions = [
            (x, y),                      # top-left
            (x + sw, y),                 # top-right
            (x + sw, y + sh),            # bottom-right
            (x, y + sh),                 # bottom-left
        ]

        for px, py in positions:
            self.canvas.create_rectangle(
                px - HANDLE_SIZE,
                py - HANDLE_SIZE,
                px + HANDLE_SIZE,
                py + HANDLE_SIZE,
                fill="white",
                outline="black",
                tags="handle"
            )

    def on_press(self, event):
        if self.image is None:
            return
        self.root.title(f"event({event.x},{event.y}) canas({self.canvas.canvasx(event.x)},{self.canvas.canvasy(event.y)})")
        #print (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), event.x, event.y)
        # Проверяем, попал ли курсор по одному из хэндлов
        handle_index = self.get_handle_index(self.canvas.canvasx(event.x),self.canvas.canvasy(event.y))
        if handle_index is not None:
            self.drag_data.update({
                "x": self.canvas.canvasx(event.x),
                "y": self.canvas.canvasy(event.y),
                "dragging": True,
                "mode": handle_index
            })
            return

        # Проверяем, попал ли курсор по изображению
        screen_x, screen_y = self.coord_system.world_to_screen(self.image_pos[0], self.image_pos[1])
        x = screen_x - self.image.width / 2 * self.computed_image_scale 
        y = screen_y - self.image.height / 2 * self.computed_image_scale
        w, h = self.image.size
        sw, sh = int(w * self.computed_image_scale), int(h * self.computed_image_scale)

        if (
            x <= self.canvas.canvasx(event.x) <= x + sw and
            y <= self.canvas.canvasy(event.y) <= y + sh
            and not self.drag_data["dragging"]
        ):
            self.drag_data.update({
                "x": self.canvas.canvasx(event.x),
                "y": self.canvas.canvasy(event.y),
                "dragging": True,
                "mode": "move"
            })
    
    def get_handle_index(self, mx, my):
        screen_x, screen_y = self.coord_system.world_to_screen(self.image_pos[0], self.image_pos[1])
        x = screen_x - self.image.width / 2 * self.computed_image_scale 
        y = screen_y - self.image.height / 2 * self.computed_image_scale
        w, h = self.image.size
        sw, sh = int(w * self.computed_image_scale), int(h * self.computed_image_scale)

        corners = [
            (x, y),                  # top-left
            (x + sw, y),             # top-right
            (x + sw, y + sh),        # bottom-right
            (x, y + sh),             # bottom-left
        ]

        for i, (cx, cy) in enumerate(corners):
            if abs(mx - cx) <= HANDLE_SIZE * 3 and abs(my - cy) <= HANDLE_SIZE * 3:
                return i
        return None


    def on_drag(self, event):
        dx = self.canvas.canvasx(event.x) - self.drag_data["x"]
        dy = self.canvas.canvasy(event.y) - self.drag_data["y"]
        if self.drag_data["mode"] == "move":
            self.image_pos[0] += dx / self.global_scale
            self.image_pos[1] -= dy / self.global_scale
        elif isinstance(self.drag_data["mode"], int):
            corner = self.drag_data["mode"]
            self.resize_image(corner, self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

        #print(f"dragging {self.drag_data["mode"]} {event.x} {event.y}")
        self.drag_data.update({"x": self.canvas.canvasx(event.x), "y": self.canvas.canvasy(event.y)})
        self.update_canvas()
        self.show_info()

    def resize_image(self, corner, mx, my):
        screen_x, screen_y = self.coord_system.world_to_screen(self.image_pos[0], self.image_pos[1])
        x = screen_x - self.image.width / 2 * self.computed_image_scale 
        y = screen_y - self.image.height / 2 * self.computed_image_scale
        w, h = self.image.size
        sw, sh = int(w * self.image_scale), int(h * self.image_scale)

        # Вычисляем новые координаты угла
        if corner == 0:  # top-left
            new_w = sw + (x - mx)
            new_h = sh + (y - my)
        elif corner == 1:  # top-right
            new_w = mx - x
            new_h = sh + (y - my)
        elif corner == 2:  # bottom-right
            new_w = mx - x
            new_h = my - y
        elif corner == 3:  # bottom-left
            new_w = sw + (x - mx)
            new_h = my - y
        # Пропорциональное изменение
        aspect = w / h
        if new_w / new_h > aspect:
            new_h = new_w / aspect
        else:
            new_w = new_h * aspect

        self.image_scale = new_w / w / self.global_scale

    def on_release(self, event):
        self.drag_data.update({"dragging": False, "mode": None})

    # перемещение по canvas с помощью мыши
    # def on_press(self, event):
    #     self.last_x = event.x
    #     self.last_y = event.y
    # def on_drag(self, event):
    #     dx = event.x - self.last_x
    #     dy = event.y - self.last_y
    #     self.translation[0] += dx
    #     self.translation[1] += dy
    #     self.last_x = event.x
    #     self.last_y = event.y
    #     self.update_canvas()

    def on_mousewheel(self,event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    def on_mousewheel_alt(self,event):
        self.canvas.xview_scroll(int(-1*(event.delta/120)), "units")
        self.h_scroll.focus()
    def on_mousewheel_ctrl(self,event):
        
        amnt = event.delta/240
        if (amnt > 0):
            self.global_scale *= (amnt+1)
        elif (amnt < 0):
            self.global_scale *= 1/(abs(amnt)+1)

    # def img_up(self):
    #     self.image_pos = [self.image_pos[0],self.image_pos[1]-5]
    # def img_down(self):
    #     self.image_pos = [self.image_pos[0],self.image_pos[1]+5]
    # def img_left(self):
    #     self.image_pos = [self.image_pos[0]-5,self.image_pos[1]]
    # def img_right(self):
    #     self.image_pos = [self.image_pos[0]+5,self.image_pos[1]] 
     
        
    def show_info(self):
        if not self.image:
            return
        
        screen_x, screen_y = self.coord_system.world_to_screen(self.image_pos[0], self.image_pos[1])
        world_x, world_y = self.coord_system.screen_to_world(screen_x, screen_y)

        info_text = (
            f"Формат: {self.image.format}\n"
            f"Размер оригинала: {self.image.size}\n"
            f"Текущий размер: {tuple(int(x * self.computed_image_scale) for x in self.image.size)}\n"
            f"Цветовая модель: {self.image.mode}\n"
            f"Масштаб: {self.image_scale:.2f}x\n"
            f"Позиция: {self.image_pos[0]:.2f}, {self.image_pos[1]:.2f}\n"
            f"world_to_screen: {screen_x:.2f}, {screen_y:.2f}\n"
            f"screen_to_world : {world_x:.2f}, {world_y:.2f}\n"
        )
        self.info_label.config(text=info_text)
    
    def handle_drop_event(self, event):
        try:
            # Извлекаем пути к файлам из данных события
            files = self.root.tk.splitlist(event.data)
            pdf_path = None
            image_path = None

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext == ".pdf":
                    pdf_path = file
                elif ext in [".png", ".jpg", ".jpeg", ".bmp"]:
                    image_path = file

            # Логика обработки
            if len(files) == 1:
                if pdf_path:
                    self.load_pdf_from_path(pdf_path)
                elif image_path:
                    self.load_image_from_path(image_path)
            elif len(files) >= 2:
                # Попробуем найти PDF и изображение
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext == ".pdf" and not pdf_path:
                        pdf_path = file
                    elif ext in [".png", ".jpg", ".jpeg", ".bmp"] and not image_path:
                        image_path = file

                if pdf_path and image_path:
                    self.load_pdf_from_path(pdf_path)
                    self.load_image_from_path(image_path)
                else:
                    messagebox.showwarning("Файлы", "Перетащите PDF и изображение.")
            else:
                messagebox.showwarning("Файлы", "Неподдерживаемый тип файла.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать файл: {e}")
            
    def load_pdf_from_path(self, path):
        try:
            self.pdf_doc = fitz.open(path)
            #messagebox.showinfo("Загрузка", f"PDF '{os.path.basename(path)}' успешно загружен.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить PDF: {e}")

    def load_image_from_path(self, path):
        try:
            self.image = Image.open(path)
            self.image_original_size = self.image.size
            self.image_pos = [0, 0]
            self.image_scale = 1
            self.save_btn.config(state=tk.NORMAL)
            self.show_info()
            #messagebox.showinfo("Загрузка", f"Изображение '{os.path.basename(path)}' загружено.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить изображение: {e}")

if __name__ == "__main__":
    root = tkinterDnD.Tk()
    root.state('zoomed')
    app = ImageEditor(root)
    root.mainloop()
