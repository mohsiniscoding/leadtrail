from leadtrail.portal.utils import snov_client
from leadtrail.portal.utils.snov_client import SnovClient

client = SnovClient()



linkedin_urls = [
    "https://uk.linkedin.com/in/wisetax-accountants-555133124",
    "https://uk.linkedin.com/in/abdul-s-abbasi",
    "https://uk.linkedin.com/in/manraj-sidhu-06b8892b6",
    "https://uk.linkedin.com/in/sami-naseem-5b0638252",
    "https://pk.linkedin.com/in/ali-sajjad-708292202",
    "https://uk.linkedin.com/in/henry-wong-2a915b146",
    "https://uk.linkedin.com/in/anastasios-anastasiou-a7321b214",
    "https://uk.linkedin.com/in/protea-melas",
    "https://uk.linkedin.com/in/khaled-ghazi-619666154",
    "https://uk.linkedin.com/in/michaeldfeiner",
    "https://za.linkedin.com/in/siphesihle-maloi-9962a3353",
    "https://za.linkedin.com/in/abdullah-abrahams-979766325",
    "https://pk.linkedin.com/in/muhammadawaisali-acca",
    "https://za.linkedin.com/in/jaime-roman-890514350",
    "https://pk.linkedin.com/in/muhammad-shuaib-acca-3a243117b",
    "https://pk.linkedin.com/in/athar-tasneem-09a296b5",
    "https://uk.linkedin.com/in/kathy-webb-london",
    "https://linkedin.com/in/velichkafilipova",
    "https://uk.linkedin.com/in/velichkafilipova",
    "https://www.linkedin.com/in/celinewood",
    "https://www.linkedin.com/in/keithwoodfca",
    "https://uk.linkedin.com/in/celinewood",
    "https://uk.linkedin.com/in/keithwoodfca",
    "https://uk.linkedin.com/in/irene-rea-320b205",
    "https://linkedin.com/in/pengge",
    "https://uk.linkedin.com/in/shuhan-liu-80710719a",
    "https://uk.linkedin.com/in/sam-whittington-a0a63a171",
    "https://uk.linkedin.com/in/muddssar-s-74782039"
]

print(client.get_balance())

for url in linkedin_urls:
    print(client.add_url_for_search(url))
    print(client.get_emails_from_url(url))

print(client.get_balance())