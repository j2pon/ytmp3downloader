import os
import re
import time
import sys
import signal
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import yt_dlp

try:
    import pyfiglet
    from pyfiglet import Figlet
    import gradient_figlet as gf
    from colour import Color
    HAS_FIGLET = True
except ImportError:
    HAS_FIGLET = False


# Renk kodları (ANSI)
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    
    # Arka plan renkleri
    BG_RED = '\033[101m'
    BG_GREEN = '\033[102m'
    BG_YELLOW = '\033[103m'
    BG_BLUE = '\033[104m'
    BG_MAGENTA = '\033[105m'
    BG_CYAN = '\033[106m'

# Gradient renk fonksiyonu
def gradient_text(text, offset=0):
    """Gökkuşağı gradient efekti ile metin oluşturur"""
    colors = [
        '\033[91m',  # Kırmızı
        '\033[93m',  # Sarı
        '\033[92m',  # Yeşil
        '\033[96m',  # Cyan
        '\033[94m',  # Mavi
        '\033[95m',  # Magenta
    ]
    
    result = ""
    for i, char in enumerate(text):
        if char == ' ':
            result += char
        else:
            color_idx = (i + offset) % len(colors)
            result += f"{colors[color_idx]}{char}{Colors.RESET}"
    return result

def rainbow_border(width=60, offset=0):
    """Gökkuşağı kenarlık oluşturur"""
    colors = ['\033[91m', '\033[93m', '\033[92m', '\033[96m', '\033[94m', '\033[95m']
    border = ""
    for i in range(width):
        color_idx = (i + offset) % len(colors)
        border += f"{colors[color_idx]}={Colors.RESET}"
    return border

def extract_video_id(url):
    """YouTube URL'sinden video ID'sini çıkarır ve temiz URL oluşturur"""
    # Farklı YouTube URL formatlarını destekle
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            # Temiz URL oluştur (playlist parametrelerini kaldır)
            return f"https://www.youtube.com/watch?v={video_id}"
    
    return None

def is_youtube_url(url):
    """URL'nin YouTube linki olup olmadığını kontrol eder"""
    if not url or url.strip().startswith('#'):
        return False
    
    # Tüm YouTube URL formatlarını kontrol et
    youtube_patterns = [
        r'youtube\.com',
        r'youtu\.be',
    ]
    
    return any(re.search(pattern, url, re.IGNORECASE) for pattern in youtube_patterns)

def read_links_from_file(file_path):
    """Txt dosyasından YouTube linklerini okur ve temizler"""
    links = []
    seen_ids = set()  # Tekrar eden videoları önlemek için
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Yorum satırlarını ve boş satırları atla
                if not line or line.startswith('#'):
                    continue
                
                if is_youtube_url(line):
                    clean_url = extract_video_id(line)
                    if clean_url:
                        # Video ID'sini çıkar ve tekrar kontrolü yap
                        video_id = re.search(r'v=([a-zA-Z0-9_-]{11})', clean_url)
                        if video_id:
                            vid_id = video_id.group(1)
                            if vid_id not in seen_ids:
                                seen_ids.add(vid_id)
                                links.append(clean_url)
        
        return links
    except FileNotFoundError:
        print(f"Hata: {file_path} dosyası bulunamadı!")
        return []
    except Exception as e:
        print(f"Dosya okuma hatası: {e}")
        return []

def is_already_downloaded(video_title, output_dir):
    """Şarkının zaten indirilip indirilmediğini kontrol eder"""
    if not video_title or video_title == 'Bilinmeyen' or not os.path.exists(output_dir):
        return False
    
    # yt-dlp dosya adı formatını taklit et: %(title)s.%(ext)s
    # Özel karakterleri temizle (Windows için)
    safe_title = re.sub(r'[<>:"/\\|?*]', '', video_title)
    mp3_path = os.path.join(output_dir, f"{safe_title}.mp3")
    
    # Tam eşleşme kontrolü
    if os.path.exists(mp3_path):
        return True
    
    # Kısmi eşleşme kontrolü (dosya adı değişmiş olabilir)
    # Klasördeki tüm mp3 dosyalarını kontrol et
    try:
        for file in os.listdir(output_dir):
            if file.endswith('.mp3'):
                # Dosya adının başlangıcını kontrol et (title'ın ilk kısmı)
                file_base = os.path.splitext(file)[0]
                if safe_title[:30].lower() in file_base.lower() or file_base[:30].lower() in safe_title.lower():
                    return True
    except Exception:
        pass
    
    return False

def download_mp3(url, output_dir, max_retries=3, retry_delay=5):
    """YouTube videosunu MP3 olarak indirir (retry mekanizması ile)"""
    # yt-dlp yapılandırması - sessiz mod
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': True,  # Tüm debug mesajlarını kapat
        'no_warnings': True,  # Uyarıları kapat
        'noplaylist': True,  # Sadece tek videoyu indir, playlist'i değil
        'extract_flat': False,
        'ignoreerrors': False,
    }
    
    # Önce video bilgilerini al
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'Bilinmeyen')
    except Exception:
        video_title = 'Bilinmeyen'
    
    # Zaten indirilmiş mi kontrol et
    if is_already_downloaded(video_title, output_dir):
        print(f"{Colors.YELLOW}⊘ Zaten indirilmiş: {video_title}{Colors.RESET}")
        print(f"  {Colors.CYAN}{url}{Colors.RESET}")
        return True
    
    # Retry mekanizması ile indir
    for attempt in range(max_retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Video bilgilerini tekrar al (her denemede)
                info = ydl.extract_info(url, download=False)
                video_title = info.get('title', 'Bilinmeyen')
                
                # İndir
                ydl.download([url])
                print(f"{Colors.GREEN}✓ {video_title}{Colors.RESET}")
                print(f"  {Colors.CYAN}{url}{Colors.RESET}")
                return True
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            
            # 403 hatası kontrolü
            if '403' in error_msg or 'forbidden' in error_msg.lower():
                if attempt < max_retries - 1:
                    print(f"{Colors.YELLOW}⚠ 403 hatası, {retry_delay} saniye bekleniyor... (Deneme {attempt + 1}/{max_retries}){Colors.RESET}")
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"{Colors.RED}✗ İndirme hatası (403 - Tüm denemeler başarısız){Colors.RESET}")
                    print(f"  {Colors.CYAN}{url}{Colors.RESET}")
                    return False
            
            # FFmpeg hatası
            if 'ffprobe' in error_msg.lower() or 'ffmpeg' in error_msg.lower():
                print(f"{Colors.RED}✗ FFmpeg hatası: FFmpeg kurulu değil{Colors.RESET}")
                print(f"  {Colors.CYAN}{url}{Colors.RESET}")
                return False
            
            # Diğer hatalar
            if attempt < max_retries - 1:
                print(f"{Colors.YELLOW}⚠ Hata, {retry_delay} saniye bekleniyor... (Deneme {attempt + 1}/{max_retries}){Colors.RESET}")
                time.sleep(retry_delay)
                continue
            else:
                print(f"{Colors.RED}✗ İndirme hatası{Colors.RESET}")
                print(f"  {Colors.CYAN}{url}{Colors.RESET}")
                return False
                
        except KeyboardInterrupt:
            # Sessizce çık, hata gösterme
            return False
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"{Colors.YELLOW}⚠ Hata, {retry_delay} saniye bekleniyor... (Deneme {attempt + 1}/{max_retries}){Colors.RESET}")
                time.sleep(retry_delay)
                continue
            else:
                print(f"{Colors.RED}✗ Hata{Colors.RESET}")
                print(f"  {Colors.CYAN}{url}{Colors.RESET}")
                return False
    
    return False

def print_menu(offset=0):
    """Gradient/gökkuşağı efektli menüyü gösterir (pyfiglet ile)"""
    os.system('cls' if os.name == 'nt' else 'clear')  # Ekranı temizle
    
    # Gradient renkleri: kırmızı -> sarı -> yeşil -> cyan -> mavi -> magenta
    gradient_colors = [
        Color("#FF0000"),  # Kırmızı
        Color("#FFFF00"),  # Sarı
        Color("#00FF00"),  # Yeşil
        Color("#00FFFF"),  # Cyan
        Color("#0000FF"),  # Mavi
        Color("#FF00FF"),  # Magenta
    ]
    
    if HAS_FIGLET:
        try:
            # Gökkuşağı kenarlık - gradient-figlet ile
            border_line = "=" * 66
            start_border_color = gradient_colors[offset % len(gradient_colors)]
            end_border_color = gradient_colors[(offset + 3) % len(gradient_colors)]
            gf.print_with_gradient(border_line, start_border_color, end_border_color)
            
            # Başlık - pyfiglet ve gradient-figlet ile
            f = Figlet(font='slant')
            ascii_text = f.renderText('J2PON YTMP3')
            
            start_color = gradient_colors[offset % len(gradient_colors)]
            end_color = gradient_colors[(offset + 3) % len(gradient_colors)]
            
            # Gradient efektli başlığı yazdır
            gf.print_with_gradient(ascii_text, start_color, end_color)
            
            # Alt başlık - gradient-figlet ile (ortalanmış)
            subtitle_text = "🎵 J2PON YOUTUBE MP3 İNDİRİCİ 🎵"
            border_width = 66
            text_width = len(subtitle_text)
            padding = (border_width - text_width) // 2
            subtitle = " " * padding + subtitle_text
            gf.print_with_gradient(subtitle, start_color, end_color)
            print()
            
            # Alt çizgi
            gf.print_with_gradient(border_line, start_border_color, end_border_color)
            print()
            
            # Menü seçenekleri - gradient-figlet ile
            menu_items = [
                ("[1]", "📥 Tek Link İndir (solo_download)"),
                ("[2]", "📚 Toplu İndir (links.txt - mp3_downloads)"),
                ("[3]", "✨ MP3 İsimlerini Sadeleştir"),
                ("[0]", "❌ Çıkış"),
            ]
            
            for num, desc in menu_items:
                menu_text = f"{num} {desc}"
                item_start = gradient_colors[(offset + 2) % len(gradient_colors)]
                item_end = gradient_colors[(offset + 5) % len(gradient_colors)]
                gf.print_with_gradient(menu_text, item_start, item_end)
            
            print()
            # Alt çizgi
            gf.print_with_gradient(border_line, start_border_color, end_border_color)
            print()
            
        except Exception as e:
            # Hata durumunda eski yöntemi kullan
            border = rainbow_border(66, offset)
            print(f"\n{border}")
            title_text = "🎵 J2PON YOUTUBE MP3 İNDİRİCİ 🎵"
            border_width = 66
            text_width = len(title_text)
            padding = (border_width - text_width) // 2
            title = " " * padding + title_text
            print(f"{gradient_text(title, offset)}\n")
            print(f"{border}\n")
            
            menu_items = [
                ("[1]", "📥 Tek Link İndir (solo_download)"),
                ("[2]", "📚 Toplu İndir (links.txt - mp3_downloads)"),
                ("[3]", "✨ MP3 İsimlerini Sadeleştir"),
                ("[0]", "❌ Çıkış"),
            ]
            
            for num, desc in menu_items:
                num_gradient = gradient_text(num, offset + 10)
                desc_gradient = gradient_text(desc, offset + 15)
                print(f"{num_gradient} {desc_gradient}")
            
            print(f"\n{border}\n")
    else:
        # Modül yüklü değilse eski yöntemi kullan
        border = rainbow_border(66, offset)
        print(f"\n{border}")
        title_text = "🎵 J2PON YOUTUBE MP3 İNDİRİCİ 🎵"
        border_width = 66
        text_width = len(title_text)
        padding = (border_width - text_width) // 2
        title = " " * padding + title_text
        print(f"{gradient_text(title, offset)}\n")
        print(f"{border}\n")
        
        menu_items = [
            ("[1]", "📥 Tek Link İndir (solo_download)"),
            ("[2]", "📚 Toplu İndir (links.txt - mp3_downloads)"),
            ("[3]", "✨ MP3 İsimlerini Sadeleştir"),
            ("[0]", "❌ Çıkış"),
        ]
        
        for num, desc in menu_items:
            num_gradient = gradient_text(num, offset + 10)
            desc_gradient = gradient_text(desc, offset + 15)
            print(f"{num_gradient} {desc_gradient}")
        
        print(f"\n{border}\n")

def download_single_link():
    """Tek link indirme fonksiyonu"""
    output_folder = "solo_download"
    Path(output_folder).mkdir(exist_ok=True)
    
    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.MAGENTA}{Colors.BOLD}📥 Tek Link İndirme{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    url = input(f"{Colors.YELLOW}YouTube linkini girin: {Colors.RESET}").strip()
    
    if not url:
        print(f"{Colors.RED}❌ Link girilmedi!{Colors.RESET}\n")
        input(f"{Colors.CYAN}Devam etmek için Enter'a basın...{Colors.RESET}")
        return
    
    if not is_youtube_url(url):
        print(f"{Colors.RED}❌ Geçersiz YouTube linki!{Colors.RESET}\n")
        input(f"{Colors.CYAN}Devam etmek için Enter'a basın...{Colors.RESET}")
        return
    
    clean_url = extract_video_id(url)
    if not clean_url:
        print(f"{Colors.RED}❌ Link işlenemedi!{Colors.RESET}\n")
        input(f"{Colors.CYAN}Devam etmek için Enter'a basın...{Colors.RESET}")
        return
    
    print(f"\n{Colors.BLUE}İndiriliyor...{Colors.RESET}\n")
    try:
        if download_mp3(clean_url, output_folder):
            print(f"\n{Colors.GREEN}✓ Başarıyla indirildi!{Colors.RESET}")
            print(f"{Colors.CYAN}📂 Klasör: {output_folder}{Colors.RESET}\n")
        else:
            print(f"\n{Colors.RED}✗ İndirme başarısız!{Colors.RESET}\n")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.CYAN}👋 İşlem iptal edildi.{Colors.RESET}\n")
    
    input(f"{Colors.CYAN}Devam etmek için Enter'a basın...{Colors.RESET}")

def download_batch():
    """Toplu indirme fonksiyonu"""
    links_file = "links.txt"
    output_folder = "mp3_downloads"
    
    Path(output_folder).mkdir(exist_ok=True)
    
    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.MAGENTA}{Colors.BOLD}📚 Toplu İndirme{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    print(f"{Colors.BLUE}📖 {links_file} dosyasından linkler okunuyor...{Colors.RESET}")
    links = read_links_from_file(links_file)
    
    if not links:
        print(f"{Colors.RED}❌ Hiç geçerli YouTube linki bulunamadı!{Colors.RESET}\n")
        input(f"{Colors.CYAN}Devam etmek için Enter'a basın...{Colors.RESET}")
        return
    
    print(f"{Colors.GREEN}✅ {len(links)} adet link bulundu.{Colors.RESET}\n")
    
    # Her linki indir
    success_count = 0
    try:
        for i, link in enumerate(links, 1):
            print(f"{Colors.CYAN}[{i}/{len(links)}]{Colors.RESET} ", end="")
            if download_mp3(link, output_folder):
                success_count += 1
            print()
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 Tamamlandı! {success_count}/{len(links)} şarkı başarıyla indirildi.{Colors.RESET}")
        print(f"{Colors.CYAN}📂 Dosyalar '{output_folder}' klasöründe.{Colors.RESET}\n")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.CYAN}👋 İşlem iptal edildi. {success_count} şarkı indirildi.{Colors.RESET}\n")
    
    input(f"{Colors.CYAN}Devam etmek için Enter'a basın...{Colors.RESET}")

def simplify_mp3_names():
    """MP3 dosya isimlerini sadeleştirir (sadece - kullanarak)"""
    output_folder = "mp3_downloads"
    
    if not os.path.exists(output_folder):
        print(f"{Colors.RED}❌ {output_folder} klasörü bulunamadı!{Colors.RESET}\n")
        input(f"{Colors.CYAN}Devam etmek için Enter'a basın...{Colors.RESET}")
        return
    
    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.MAGENTA}{Colors.BOLD}✨ MP3 İsimlerini Sadeleştirme{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    mp3_files = [f for f in os.listdir(output_folder) if f.endswith('.mp3')]
    
    if not mp3_files:
        print(f"{Colors.YELLOW}⚠ {output_folder} klasöründe MP3 dosyası bulunamadı!{Colors.RESET}\n")
        input(f"{Colors.CYAN}Devam etmek için Enter'a basın...{Colors.RESET}")
        return
    
    print(f"{Colors.BLUE}📁 {len(mp3_files)} adet MP3 dosyası bulundu.{Colors.RESET}\n")
    
    renamed_count = 0
    for filename in mp3_files:
        old_path = os.path.join(output_folder, filename)
        name, ext = os.path.splitext(filename)
        
        # Sadeleştirme: Özel karakterleri kaldır, sadece - kullan
        # Boşlukları - ile değiştir, birden fazla -'yi tek - yap
        simplified = re.sub(r'[<>:"/\\|?*]', '', name)  # Özel karakterleri kaldır
        simplified = re.sub(r'\s+', '-', simplified)  # Boşlukları - ile değiştir
        simplified = re.sub(r'-+', '-', simplified)  # Birden fazla -'yi tek yap
        simplified = simplified.strip('-')  # Başta ve sonda - varsa kaldır
        
        new_filename = f"{simplified}{ext}"
        new_path = os.path.join(output_folder, new_filename)
        
        # Eğer isim değiştiyse yeniden adlandır
        if filename != new_filename:
            try:
                # Eğer aynı isimde dosya varsa atla
                if os.path.exists(new_path):
                    print(f"{Colors.YELLOW}⊘ Atlandı (zaten var): {new_filename}{Colors.RESET}")
                    continue
                
                os.rename(old_path, new_path)
                print(f"{Colors.GREEN}✓ {filename}{Colors.RESET}")
                print(f"  {Colors.CYAN}→ {new_filename}{Colors.RESET}")
                renamed_count += 1
            except Exception as e:
                print(f"{Colors.RED}✗ Hata ({filename}): {e}{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}⊘ Değişiklik yok: {filename}{Colors.RESET}")
    
    print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 Tamamlandı! {renamed_count} dosya yeniden adlandırıldı.{Colors.RESET}\n")
    input(f"{Colors.CYAN}Devam etmek için Enter'a basın...{Colors.RESET}")

def signal_handler(sig, frame):
    """Ctrl+C için temiz çıkış"""
    print(f"\n\n{Colors.CYAN}👋 İşlem iptal edildi. Görüşmek üzere!{Colors.RESET}\n")
    sys.exit(0)

def main():
    """Ana menü döngüsü"""
    # Signal handler'ı ayarla (Ctrl+C için)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Windows için ANSI renk desteğini etkinleştir
    if os.name == 'nt':
        os.system('')
    
    offset = 0
    while True:
        try:
            print_menu(offset)
            offset = (offset + 1) % 6  # Gradient animasyonu için offset güncelle
            
            choice = input(f"{Colors.YELLOW}Seçiminizi yapın (0-3): {Colors.RESET}").strip()
            
            if choice == '1':
                download_single_link()
            elif choice == '2':
                download_batch()
            elif choice == '3':
                simplify_mp3_names()
            elif choice == '0':
                print(f"\n{Colors.CYAN}👋 Görüşmek üzere!{Colors.RESET}\n")
                break
            else:
                print(f"\n{Colors.RED}❌ Geçersiz seçim! Lütfen 0-3 arası bir sayı girin.{Colors.RESET}\n")
                time.sleep(1)
        except KeyboardInterrupt:
            # Menüde Ctrl+C basıldığında
            print(f"\n\n{Colors.CYAN}👋 Görüşmek üzere!{Colors.RESET}\n")
            sys.exit(0)
        except EOFError:
            # Ctrl+Z için
            print(f"\n\n{Colors.CYAN}👋 Görüşmek üzere!{Colors.RESET}\n")
            sys.exit(0)

if __name__ == "__main__":
    main()

