import os
from PIL import Image, ImageOps

def apply_watermark(base_image_path: str, watermark_path: str = "watermark.png") -> str:
    """
    Applies a watermark frame to the base image.
    The script will center the product photo inside a white canvas matching the frame size,
    and overlay the frame on top.
    """
    # Garante que o caminho do watermark seja absoluto
    if not os.path.isabs(watermark_path):
        watermark_path = os.path.join(os.getcwd(), watermark_path)

    if not os.path.exists(base_image_path) or not os.path.exists(watermark_path):
        print(f"⚠️ Watermark ou base não encontrados: {base_image_path}, {watermark_path}")
        return base_image_path
        
    # Ignora o arquivo se ele estiver vazio (como nosso placeholder)
    if os.path.getsize(watermark_path) < 100:
        return base_image_path
        
    try:
        base_img = Image.open(base_image_path).convert("RGBA")
        frame = Image.open(watermark_path).convert("RGBA")
        
        # O tamanho final será exatamente igual ao tamanho do frame (PNG do usuário)
        frame_w, frame_h = frame.size
        
        # Cria um canvas com fundo branco sólido
        canvas = Image.new("RGBA", (frame_w, frame_h), (255, 255, 255, 255))
        
        # Analisa a proporção para decidir o nível de zoom out
        base_ratio = base_img.width / base_img.height
        is_horizontal = base_ratio > 1.05 # Maior que 1 significa horizontal (largura > altura)
        
        # O usuário quer um "zoom out" maior se a imagem for horizontal
        zoom_factor = 0.75 if is_horizontal else 0.90
            
        target_size = (int(frame_w * zoom_factor), int(frame_h * zoom_factor))
        
        # Redimensiona mantendo a proporção (thumbnail) para não distorcer o produto
        base_img.thumbnail(target_size, Image.Resampling.LANCZOS)
        
        # Calcula a posição centralizada no canvas
        pos_x = (frame_w - base_img.width) // 2
        
        # Para imagens horizontais podemos deixá-las um pouquinho mais centralizadas ou no meio.
        # Por padrão a divisão por 2 já centraliza tudo perfeitamente.
        pos_y = (frame_h - base_img.height) // 2
        
        # Cola o produto centralizado no canvas usando a própria base_img como máscara
        # Se for um JPG ou não tiver canal alpha, criamos uma máscara opaca
        if base_img.mode == 'RGBA':
            canvas.paste(base_img, (pos_x, pos_y), base_img)
        else:
            canvas.paste(base_img, (pos_x, pos_y))
        
        # Cola a Moldura (Frame transparente) por cima de tudo
        canvas.paste(frame, (0, 0), frame)
        
        new_path = base_image_path.rsplit('.', 1)[0] + "_wm.png"
        canvas.save(new_path, "PNG")
        
        return new_path
        
    except Exception as e:
        print(f"Erro ao aplicar frame: {e}")
        return base_image_path
