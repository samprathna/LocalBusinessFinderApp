import streamlit as st
import pandas as pd
import googlemaps
import time
from geopy.distance import geodesic
import requests
from bs4 import BeautifulSoup
import re

# Email extraction function

def find_emails_from_website(base_url):
    if not base_url:
        return None, None

    found_emails = set()
    facebook_url = None
    checked_urls = set()
    request_count = 0
    MAX_MAIN_REQUESTS = 5
    FACEBOOK_REQUESTS = 1

    # Standard pages to try first
    pages_to_try = pages_to_try = [
    '',

    # Contact variations
    '/contact', '/contact-us', '/contacts', '/nous-joindre', '/joindre',  'nous_joindre'
    '/contact_us', '/contactez-nous', '/contactez_nous',
    '/soumission', '/quote', '/request-a-quote', '/demande',

    # About variations
    '/about', '/about-us', '/about_us', '/a-propos', '/a_propos', '/apropos', '/qui-sommes-nous',

    # Support or info
    '/support', '/help', '/aide', '/faq', '/info', '/information',
    '/customer-service', '/service-client', '/services',

    # PHP versions
    '/contact.php', '/contact-us.php', '/contacts.php', '/nous-joindre.php', '/soumission.php',
    '/about.php', '/about-us.php', '/a-propos.php', '/apropos.php',
    '/support.php', '/help.php', '/faq.php', '/info.php', '/services.php',
    '/reservation.php', '/booking.php',

    # HTML versions
    '/contact.html', '/contact-us.html', '/contacts.html', '/nous-joindre.html', '/soumission.html',
    '/about.html', '/about-us.html', '/a-propos.html', '/apropos.html',
    '/support.html', '/help.html', '/faq.html', '/info.html', '/services.html',
    '/reservation.html', '/booking.html'
]

    def scrape_page(url):
        nonlocal request_count, facebook_url
        if request_count >= MAX_MAIN_REQUESTS or url in checked_urls:
            return
        checked_urls.add(url)

        try:
            response = requests.get(url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
            request_count += 1
            time.sleep(1)  # delay between requests
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                text = soup.get_text()
                emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
                for email in emails:
                    if not email.lower().endswith(('.png', '.jpg', '.jpeg')):
                        found_emails.add(email)

                # Find Facebook link
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

    # 1. Scrape up to 5 from the main site
    for path in pages_to_try:
        if request_count >= MAX_MAIN_REQUESTS:
            break
        full_url = base_url.rstrip('/') + path
        scrape_page(full_url)

    # 2. Collect shallow internal links from homepage (only if space left)
    if request_count < MAX_MAIN_REQUESTS:
        try:
            response = requests.get(base_url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
            time.sleep(1)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                internal_links = [
                    a['href'] for a in soup.find_all('a', href=True)
                    if (
                        (a['href'].startswith('/') or base_url in a['href']) and
                        a['href'].count('/') <= 2
                    )
                ]
                for link in internal_links:
                    if request_count >= MAX_MAIN_REQUESTS:
                        break
                    if link.startswith('/'):
                        link = base_url.rstrip('/') + link
                    scrape_page(link)
        except:
            pass

    # 3. If still no email, try Facebook
    if not found_emails and facebook_url:
        try:
            response = requests.get(facebook_url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
            time.sleep(1)
            if response.status_code == 200:
                text = response.text
                emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
                for email in emails:
                    if not email.lower().endswith(('.png', '.jpg', '.jpeg')):
                        found_emails.add(email)
        except:
            pass

    return ', '.join(found_emails) if found_emails else None, facebook_url

# Business search function

def FindLocalBusinesses(radius, keyword, postalcode, api_key):
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
    for place in all_results:
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

        business_data.append([
            name, reviews, rating, distance_km, website, address, phone, email, facebook
        ])
        time.sleep(0.1)

    df = pd.DataFrame(
        business_data,
        columns=[
            "Business Name", "Number of Reviews", "Star Rating", "Distance (km)",
            "Website", "Address", "Phone Number", "Email Address", "Facebook Page"
        ]
    )
    return df.reset_index(drop=True)

# Streamlit app interface

def main():
    st.title("Local Business Finder")

    radius = st.number_input("Enter the search radius (in km):", min_value=1, max_value=100, value=10)
    keyword = st.text_input("Enter the business keyword (e.g., plumber, dentist):")
    postalcode = st.text_input("Enter the postal code (e.g., H2E 2M6):")

    api_key = st.secrets.get("google", {}).get("api_key", None)

    if st.button("Find Businesses"):
        if not keyword or not postalcode or not api_key:
            st.error("Please fill out all fields and make sure your API key is set in Streamlit secrets!")
        else:
            try:
                df = FindLocalBusinesses(radius, keyword, postalcode, api_key)
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
