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
        return None

    pages_to_try = ['', '/contact', '/about', '/a-propos', '/contacts', 'about_us', 'about-us', 'contact-us']
    found_emails = set()

    for path in pages_to_try:
        try:
            url = base_url.rstrip('/') + path
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                text = soup.get_text()
                emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
                for email in emails:
                    if not email.endswith(('.png', '.jpg', '.jpeg')):
                        found_emails.add(email)
        except:
            continue

    return ', '.join(found_emails) if found_emails else None


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

        if place_id:
            try:
                details = gmaps.place(place_id=place_id, fields=[
                    'website', 'formatted_address', 'formatted_phone_number'
                ])
                result = details.get('result', {})
                website = result.get('website')
                address = result.get('formatted_address')
                phone = result.get('formatted_phone_number')

                # Attempt to extract email from the business website
                if website:
                    email = find_emails_from_website(website)

            except Exception as e:
                print(f"Error getting details for {name}: {e}")

        business_data.append([
            name, reviews, rating, distance_km, website, address, phone, email
        ])
        time.sleep(0.1)

    df = pd.DataFrame(
        business_data,
        columns=[
            "Business Name",
            "Number of Reviews",
            "Star Rating",
            "Distance (km)",
            "Website",
            "Address",
            "Phone Number",
            "Email Address"
        ]
    )
    return df.reset_index(drop=True)


# Streamlit app interface
def main():
    st.title("Local Business Finder")

    # Get user input
    radius = st.number_input("Enter the search radius (in km):", min_value=1, max_value=100, value=10)
    keyword = st.text_input("Enter the business keyword (e.g., plumber, dentist):")
    postalcode = st.text_input("Enter the postal code (e.g., H2E 2M6):")

    if st.button("Find Businesses"):
        if not keyword or not postalcode or not api_key:
            st.error("Please fill out all the fields!")
        else:
            try:
                df = FindLocalBusinesses(radius, keyword, postalcode, api_key)
                api_key = st.secrets["google"]["api_key"]
                if not df.empty:
                    st.write("### Found Businesses", df)
                    
                    # Option to download the results
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
