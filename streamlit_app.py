import streamlit as st
import pandas as pd
import googlemaps
import time
import requests
import re
import random
from bs4 import BeautifulSoup
from geopy.distance import geodesic
from concurrent.futures import ThreadPoolExecutor, as_completed
import streamlit.components.v1 as components

# ----------------------------
# Smart page list generator
# ----------------------------
def generate_pages_to_try():
    priority_base_paths = [
        '/contact', '/contact-us', '/contact_us', '/contacts', '/contactus',
        '/contactez-nous'
        '/about', '/about-us', '/about_us',
        '/a-propos', '/a-propos-de', '/a_propos'
    ]

    full_paths = []

    for base in priority_base_paths:
        full_paths.append(base.rstrip('/'))                         # No suffix
        full_paths.append(base.rstrip('/') + '/')                   # With slash
        full_paths.append('/pages' + base.rstrip('/'))              # /pages prefix

    return list(dict.fromkeys(full_paths))  # Remove duplicates, preserve order

# ----------------------------
# Email + Social Media scraper
# ----------------------------
def find_emails_from_website(base_url):
    if not base_url:
        return None, None, None

    found_emails = set()
    facebook_url = None
    instagram_url = None
    pages_to_try = generate_pages_to_try()
    user_agent = random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Mozilla/5.0 (X11; Linux x86_64)"
    ])
    headers = {'User-Agent': user_agent}
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

    def scrape_page(url):
        nonlocal facebook_url, instagram_url
        try:
            response = requests.get(url, timeout=5, headers=headers)
            time.sleep(random.uniform(0.6, 1.4))
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # From mailto:
                for link in soup.select('a[href^=mailto]'):
                    email = link['href'].replace('mailto:', '').strip()
                    if email:
                        found_emails.add(email)

                # From visible text
                text = soup.get_text()
                emails = re.findall(email_pattern, text)
                for email in emails:
                    if not email.lower().endswith(('.png', '.jpg', '.jpeg')):
                        found_emails.add(email)

                # Social links
                if not facebook_url:
                    fb = soup.find('a', href=re.compile(r'facebook\.com'))
                    if fb:
                        href = fb.get('href')
                        facebook_url = 'https://www.facebook.com' + href if href.startswith('/') else href

                if not instagram_url:
                    insta = soup.find('a', href=re.compile(r'instagram\.com'))
                    if insta:
                        href = insta.get('href')
                        instagram_url = 'https://www.instagram.com' + href if href.startswith('/') else href
        except:
            pass

    # Scrape homepage first
    scrape_page(base_url)

    if not found_emails:
        for path in pages_to_try:
            full_url = base_url.rstrip('/') + path
            scrape_page(full_url)
            if found_emails:
                break

    return (
        ', '.join(found_emails) if found_emails else None,
        facebook_url,
        instagram_url
    )

# ----------------------------
# Process one business
# ----------------------------
def process_business(place, center_latlng, gmaps):
    name = place.get('name')
    reviews = place.get('user_ratings_total', 0)
    rating = place.get('rating', None)
    lat = place['geometry']['location']['lat']
    lng = place['geometry']['location']['lng']
    distance_km = round(geodesic(center_latlng, (lat, lng)).km, 2)

    place_id = place.get('place_id')
    website = address = phone = None
    email = facebook = instagram = None

    if place_id:
        try:
            details = gmaps.place(place_id=place_id, fields=[
                'website', 'formatted_address', 'formatted_phone_number'
            ])
            result = details.get('result', {})
            website = result.get('website')
            address = result.get('formatted_address')
            phone = result.get('formatted_phone_number')

            if website:
                email, facebook, instagram = find_emails_from_website(website)
        except Exception as e:
            print(f"Error getting details for {name}: {e}")

    return [name, reviews, rating, distance_km, website, address, phone, email, facebook, instagram]

# ----------------------------
# Business search
# ----------------------------
def FindLocalBusinesses(radius, keyword, postalcode, api_key, progress_callback=None):
    gmaps = googlemaps.Client(key=api_key)
    geocode_result = gmaps.geocode(postalcode)

    if not geocode_result:
        raise ValueError("Invalid postal code or not found.")

    location = geocode_result[0]['geometry']['location']
    center_latlng = (location['lat'], location['lng'])

    all_results = []
    next_page_token = None

    while True:
        places_result = gmaps.places_nearby(
            location=center_latlng,
            radius=radius * 1000,
            keyword=keyword,
            page_token=next_page_token
        )
        all_results.extend(places_result['results'])
        next_page_token = places_result.get('next_page_token')
        if next_page_token:
            time.sleep(2)
        else:
            break

    business_data = []
    total = len(all_results)
    completed = 0

    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = [
            executor.submit(process_business, place, center_latlng, gmaps)
            for place in all_results
        ]
        for future in as_completed(futures):
            business_data.append(future.result())
            completed += 1
            if progress_callback:
                progress_callback(completed / total)

    df = pd.DataFrame(
        business_data,
        columns=[
            "Business Name", "Number of Reviews", "Star Rating", "Distance (km)",
            "Website", "Address", "Phone Number", "Email Address",
            "Facebook Page", "Instagram Page"
        ]
    )
    return df.reset_index(drop=True)

# ----------------------------
# Streamlit App Interface
# ----------------------------
def main():
    st.set_page_config(page_title="TRW - Local Business Finder", page_icon="favicon.jpg", layout="wide")

    if "matrix_mode" not in st.session_state:
        st.session_state.matrix_mode = True

    if st.button("🧠 Escape the Matrix" if st.session_state.matrix_mode else "🔌 Enter the Matrix"):
        st.session_state.matrix_mode = not st.session_state.matrix_mode



    if st.session_state.matrix_mode:
        components.html("""
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    overflow: hidden;
                }
                canvas {
                    position: fixed;
                    top: 0;
                    left: 0;
                    z-index: -1;
                }
            </style>
            <canvas id="matrix-canvas"></canvas>
            <script>
                const canvas = document.getElementById("matrix-canvas");
                const ctx = canvas.getContext("2d");
                canvas.height = window.innerHeight;
                canvas.width = window.innerWidth;
    
                const letters = "アァイィウエオカキクケコサシスセソ0123456789";
                const fontSize = 14;
                const columns = canvas.width / fontSize;
                const drops = Array(Math.floor(columns)).fill(1);
    
                function draw() {
                    ctx.fillStyle = "rgba(0, 0, 0, 0.05)";
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    ctx.fillStyle = "#0F0";
                    ctx.font = fontSize + "px monospace";
                    for (let i = 0; i < drops.length; i++) {
                        const text = letters[Math.floor(Math.random() * letters.length)];
                        ctx.fillText(text, i * fontSize, drops[i] * fontSize);
                        if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                            drops[i] = 0;
                        }
                        drops[i]++;
                    }
                }
                setInterval(draw, 50);
            </script>
        """, height=0, width=0)

    st.markdown("""
        <h1 style="display: flex; align-items: center;">
            <img src="https://github.com/samprathna/LocalBusinessFinderApp/blob/main/favicon.jpg?raw=true" width="45" style="margin-right: 10px;">
            TRW - Local Business Finder
        </h1>
    """, unsafe_allow_html=True)

    radius = st.number_input("Search radius (km):", min_value=1, max_value=100, value=10)
    keyword = st.text_input("Business keyword (e.g., plumber, dentist):")
    postalcode = st.text_input("Postal/ZIP code (e.g., H2E 2M6 or 90210):")
    api_key = st.secrets.get("google", {}).get("api_key", None)

    if st.button("Find Businesses"):
        if not keyword or not postalcode or not api_key:
            st.error("Please fill out all fields and ensure your API key is set in Streamlit secrets.")
        else:
            try:
                progress_bar = st.progress(0)
                df = FindLocalBusinesses(
                    radius, keyword, postalcode, api_key,
                    progress_callback=lambda p: progress_bar.progress(min(p, 1.0))
                )

                if not df.empty:
                    st.success("✅ Businesses found!")
                    st.write("### Results")
                    st.dataframe(df, use_container_width=True)
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=f"businesses_{keyword}_{radius}km_{postalcode}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No businesses found.")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# ----------------------------
# Run app
# ----------------------------
if __name__ == "__main__":
    main()
