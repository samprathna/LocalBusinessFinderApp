# Make sure to have "favicon.jpg" in your repo or hosting path

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

def generate_pages_to_try():
    base_paths = [
        '/contact', '/contacts', '/contactus', '/contact-us', '/contact_us',
        '/about', '/aboutus', '/about-us', '/about_us',
        '/contactez-nous', '/a-propos', '/apropos'
    ]
    paths = set()
    paths.update(base_paths)
    paths.update([p.rstrip('/') + '/' for p in base_paths])
    paths.update(['/pages' + p.rstrip('/') for p in base_paths])
    return list(paths)

def find_emails_from_website(base_url):
    if not base_url:
        return None, None, None

    found_emails = set()
    facebook_url = None
    instagram_url = None
    pages_to_try = generate_pages_to_try()
    headers = {'User-Agent': random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Mozilla/5.0 (X11; Linux x86_64)"
    ])}
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

    def extract_data(soup):
        nonlocal facebook_url, instagram_url

        for mailto in soup.select('a[href^=mailto]'):
            email = mailto.get('href').replace('mailto:', '').strip()
            if email:
                found_emails.add(email)

        text = soup.get_text()
        for email in re.findall(email_pattern, text):
            if not email.lower().endswith(('.png', '.jpg', '.jpeg')):
                found_emails.add(email)

        if not facebook_url:
            fb = soup.find('a', href=re.compile(r'facebook\.com'))
            if fb:
                href = fb.get('href')
                facebook_url = 'https://www.facebook.com' + href if href.startswith('/') else href

        if not instagram_url:
            ig = soup.find('a', href=re.compile(r'instagram\.com'))
            if ig:
                href = ig.get('href')
                instagram_url = 'https://www.instagram.com' + href if href.startswith('/') else href

    def scrape(url):
        try:
            r = requests.get(url, timeout=5, headers=headers)
            time.sleep(random.uniform(0.6, 1.4))
            if r.status_code == 200:
                extract_data(BeautifulSoup(r.text, 'html.parser'))
        except:
            pass

    scrape(base_url.rstrip('/'))  # homepage first

    if not found_emails:
        for path in pages_to_try:
            scrape(base_url.rstrip('/') + path)
            if found_emails:
                break

    return ', '.join(found_emails) if found_emails else None, facebook_url, instagram_url

def process_business(place, center_latlng, gmaps):
    name = place.get('name')
    reviews = place.get('user_ratings_total', 0)
    rating = place.get('rating')
    lat = place['geometry']['location']['lat']
    lng = place['geometry']['location']['lng']
    distance_km = round(geodesic(center_latlng, (lat, lng)).km, 2)

    place_id = place.get('place_id')
    website = address = phone = email = facebook = instagram = None

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

def FindLocalBusinesses(radius, keyword, postalcode, api_key, progress_callback=None):
    gmaps = googlemaps.Client(key=api_key)
    geo = gmaps.geocode(postalcode)
    if not geo:
        raise ValueError("Invalid postal code")
    loc = geo[0]['geometry']['location']
    center_latlng = (loc['lat'], loc['lng'])

    all_results, next_page_token = [], None
    while True:
        res = gmaps.places_nearby(location=center_latlng, radius=radius * 1000, keyword=keyword, page_token=next_page_token)
        all_results.extend(res['results'])
        next_page_token = res.get('next_page_token')
        if next_page_token:
            time.sleep(2)
        else:
            break

    business_data, total, completed = [], len(all_results), 0
    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = [executor.submit(process_business, p, center_latlng, gmaps) for p in all_results]
        for future in as_completed(futures):
            business_data.append(future.result())
            completed += 1
            if progress_callback:
                progress_callback(completed / total)

    df = pd.DataFrame(business_data, columns=[
        "Business Name", "Number of Reviews", "Star Rating", "Distance (km)",
        "Website", "Address", "Phone Number", "Email Address", "Facebook Page", "Instagram Page"
    ])
    return df.reset_index(drop=True)

def main():
    st.set_page_config(
    page_title="TRW - Local Business Finder",
    page_icon="favicon.jpg",
    layout="wide"  # ✅ This enables full width layout
    )
    
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
                progress = st.progress(0)
                df = FindLocalBusinesses(radius, keyword, postalcode, api_key, progress_callback=lambda p: progress.progress(min(p, 1.0)))
                if not df.empty:
                    st.success("✅ Businesses found!")
                    st.write("### Results")
                    st.dataframe(df, use_container_width=True)
                    st.download_button("Download CSV", df.to_csv(index=False), file_name=f"businesses_{keyword}_{radius}km_{postalcode}.csv", mime="text/csv")
                else:
                    st.warning("No businesses found.")
            except Exception as e:
                st.error(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
