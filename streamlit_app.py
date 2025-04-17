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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (X11; Linux x86_64)",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
    "Mozilla/5.0 (iPad; CPU OS 13_2 like Mac OS X)"
]

def find_emails_from_website(base_url):
    if not base_url:
        return None, None

    found_emails = set()
    facebook_url = None
    headers = {'User-Agent': random.choice(USER_AGENTS)}

    pages_to_try = [
        '',
        '/contact', '/contact-us', '/contacts', '/contact_us', '/contactez-nous',
        '/soumission', '/devis', '/quote', '/request-a-quote',
        '/formulaire-contact', '/about', '/about-us', '/a-propos', '/apropos',
        '/support', '/help', '/aide', '/faq', '/info', '/services',
        '/reservation', '/booking', '/appointment',
        '/pages/contact', '/pages/about', '/pages/support', '/pages/faq'
    ]

    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

    def scrape_page(url):
        nonlocal facebook_url
        try:
            response = requests.get(url, timeout=5, headers=headers)
            time.sleep(random.uniform(0.6, 1.4))
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract emails from mailto links
                for mailto_link in soup.select('a[href^=mailto]'):
                    email = mailto_link.get('href').replace('mailto:', '').strip()
                    if email:
                        found_emails.add(email)

                # Extract emails from visible text
                text = soup.get_text()
                emails = re.findall(email_pattern, text)
                for email in emails:
                    if not email.lower().endswith(('.png', '.jpg', '.jpeg')):
                        found_emails.add(email)

                # Facebook link detection
                if not facebook_url:
                    fb_link = soup.find('a', href=re.compile(r'facebook\.com'))
                    if fb_link:
                        raw_href = fb_link.get('href')
                        facebook_url = (
                            'https://www.facebook.com' + raw_href if raw_href.startswith('/')
                            else raw_href
                        )
        except:
            pass

    for path in pages_to_try:
        full_url = base_url.rstrip('/') + path
        scrape_page(full_url)
        if found_emails:
            break

    return ', '.join(found_emails) if found_emails else None, facebook_url

def process_business(place, center_latlng, gmaps):
    name = place.get('name')
    reviews = place.get('user_ratings_total', 0)
    rating = place.get('rating', None)

    lat = place['geometry']['location']['lat']
    lng = place['geometry']['location']['lng']
    place_latlng = (lat, lng)
    distance_km = round(geodesic(center_latlng, place_latlng).km, 2)

    place_id = place.get('place_id')
    website = None
    address = None
    phone = None
    email = None
    facebook = None

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
                email, facebook = find_emails_from_website(website)

        except Exception as e:
            print(f"Error getting details for {name}: {e}")

    return [
        name, reviews, rating, distance_km, website, address, phone, email, facebook
    ]

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

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(process_business, place, center_latlng, gmaps)
            for place in all_results
        ]
        for future in as_completed(futures):
            result = future.result()
            business_data.append(result)
            completed += 1
            if progress_callback:
                progress_callback(completed / total)

    df = pd.DataFrame(
        business_data,
        columns=[
            "Business Name", "Number of Reviews", "Star Rating", "Distance (km)",
            "Website", "Address", "Phone Number", "Email Address", "Facebook Page"
        ]
    )
    return df.reset_index(drop=True)

def main():
    st.title("Local Business Finder")

    radius = st.number_input("Enter the search radius (in km):", min_value=1, max_value=100, value=10)
    keyword = st.text_input("Enter the business keyword (e.g., plumber, dentist):")
    postalcode = st.text_input("Enter the postal code (e.g., H7T 2L8):")
    api_key = st.secrets.get("google", {}).get("api_key", None)

    if st.button("Find Businesses"):
        if not keyword or not postalcode or not api_key:
            st.error("Please fill out all fields and make sure your API key is set in Streamlit secrets!")
        else:
            try:
                progress_bar = st.progress(0)
                df = FindLocalBusinesses(
                    radius, keyword, postalcode, api_key,
                    progress_callback=lambda p: progress_bar.progress(min(p, 1.0))
                )

                if not df.empty:
                    st.write("### Found Businesses", df)
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download results as CSV",
                        data=csv,
                        file_name=f"businesses_{keyword}_{radius}km_{postalcode}.csv",
                        mime="text/csv"
                    )
                else:
                    st.write("No businesses found.")

            except Exception as e:
                st.error(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
