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
        
        # O usuário quer um "zoom out", ou seja, que a foto do produto NÃO ocupe todo o frame.
        # Vamos redimensionar a foto do produto para que ela ocupe cerca de 90% do menor lado.
        zoom_factor = 0.90
        target_size = (int(frame_w * zoom_factor), int(frame_h * zoom_factor))
        
        # Redimensiona mantendo a proporção (thumbnail) para não distorcer o produto
        base_img.thumbnail(target_size, Image.Resampling.LANCZOS)
        
        # Calcula a posição centralizada
        pos_x = (frame_w - base_img.width) // 2
        pos_y = (frame_h - base_img.height) // 2
        
        # Cola o produto centralizado no canvas
        canvas.paste(base_img, (pos_x, pos_y), base_img if base_img.mode == 'RGBA' else None)
        
        # Cola o Frame transparente por cima de tudo
        canvas.paste(frame, (0, 0), frame)
        
        new_path = base_image_path.rsplit('.', 1)[0] + "_wm.png"
        canvas.save(new_path, "PNG")
        
        return new_path
        
    except Exception as e:
        print(f"Erro ao aplicar frame: {e}")
        return base_image_path
