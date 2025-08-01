import streamlit as st
import pandas as pd
import requests
import time
import folium
from streamlit_folium import st_folium
from dotenv import load_dotenv
import streamlit.components.v1 as components
import os
import re

# .env 파일에서 API 키 불러오기
load_dotenv()
google_api_key = os.getenv("Google_key")
naver_client_id = os.getenv("NAVER_CLIENT_ID")
naver_client_secret = os.getenv("NAVER_CLIENT_SECRET")

# 맛집 데이터 전처리 함수
def preprocess_restaurant_data(df):
    df['이름'] = df['이름'].astype(str).str.strip()
    df = df[~df['이름'].isin(['-', '없음', '', None])]
    df = df.drop_duplicates(subset='이름')
    df['평점'] = pd.to_numeric(df['평점'], errors='coerce')
    df = df.dropna(subset=['평점'])
    df['주소'] = df['주소'].astype(str).str.strip()
    df['주소'] = df['주소'].str.replace(r'^KR, ?', '', regex=True)
    df['주소'] = df['주소'].str.replace(r'^South Korea,?\s*', '', regex=True)
    df['주소'] = df['주소'].str.rstrip('/')
    df = df[~df['주소'].apply(lambda x: bool(re.fullmatch(r'[A-Za-z0-9 ,.-]+', x)))]
    df = df[df['주소'].str.strip() != '']
    df = df.dropna(subset=['주소'])
    df = df.sort_values(by='평점', ascending=False)
    return df.reset_index(drop=True)


# 관광지 이미지 검색 (네이버 이미지 API 사용)
def search_image_naver(query):
    url = "https://openapi.naver.com/v1/search/image"
    headers = {
        "X-Naver-Client-Id": naver_client_id,
        "X-Naver-Client-Secret": naver_client_secret
    }
    params = {
        "query": query,
        "display": 1,
        "sort": "sim",
        "filter": "medium"
    }

    res = requests.get(url, headers=headers, params=params)
    if res.status_code == 200:
        items = res.json().get("items")
        if items:
            return items[0].get("link")
    return None


# 관광지 → 위도/경도 변환 (Google Geocoding API)
def get_lat_lng(address, api_key):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {'address': address, 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    if res['status'] == 'OK':
        location = res['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    return None, None


# 주변 맛집 찾기 (Google Places Nearby API)
def find_nearby_restaurants(lat, lng, api_key, radius=2000):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        'location': f'{lat},{lng}',
        'radius': radius,
        'type': 'restaurant',
        'language': 'ko',
        'key': api_key
    }
    res = requests.get(url, params=params).json()
    time.sleep(1)
    results = res.get('results', [])[:15]
    restaurants = []
    for r in results:
        restaurants.append({
            '이름': r.get('name'),
            '주소': r.get('vicinity'),
            '평점': r.get('rating', '없음'),
            '위도': r['geometry']['location']['lat'],
            '경도': r['geometry']['location']['lng']
        })
    return restaurants


# 지역 기반 관광지 검색 (Google Text Search API)
def search_places(query, api_key):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {'query': f"{query} 관광지", 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    return res.get('results', [])


# 메인 앱
def main():
    st.set_page_config(page_title="관광지 주변 맛집 추천", layout="wide")
    st.title("📍 관광지 주변 맛집 추천 시스템")

    if not google_api_key or not naver_client_id or not naver_client_secret:
        st.error("❗ .env 파일에 Google/Naver API 키가 누락되었습니다.")
        return

    query = st.text_input("가고 싶은 지역을 입력하세요")

    if query:
        # 관광지 리스트 가져오기
        places = search_places(query, google_api_key)

        # 관광지 데이터프레임 구성
        places_data = []
        for p in places:
            places_data.append({
                '이름': p.get('name'),
                '주소': p.get('formatted_address'),
                '평점': p.get('rating', None)
            })
        places_df = pd.DataFrame(places_data)
        places_df['평점'] = pd.to_numeric(places_df['평점'], errors='coerce')
        places_df = places_df.dropna(subset=['평점'])
        places_df = places_df.sort_values(by='평점', ascending=False).reset_index(drop=True)

        # 관광지 표 출력
        st.subheader("🏞 지역 내 관광지 (평점순)")
        st.dataframe(places_df[['이름', '주소', '평점']].head(10))

        # 관광지 선택
        selected_place = st.selectbox("관광지를 선택하세요", places_df['이름'].tolist())

        if selected_place:
            selected_row = places_df[places_df['이름'] == selected_place].iloc[0]
            address = selected_row['주소']
            rating = selected_row['평점']

            st.markdown(f"### 🏞 관광지: {selected_place}")
            st.write(f"📍 주소: {address}")
            st.write(f"⭐ 평점: {rating}")

            # ✅ 이미지 검색
            image_url = search_image_naver(selected_place)
            if image_url:
                st.image(image_url, caption=f"{selected_place} 관련 이미지", use_column_width=True)
            else:
                st.warning("이미지를 찾을 수 없습니다.")

            # 좌표 변환 → 맛집 검색
            lat, lng = get_lat_lng(address, google_api_key)
            if lat is None:
                st.error("위치 정보를 불러오지 못했습니다.")
                return

            st.subheader("🍽 주변 3km 맛집 Top 10")
            restaurants = find_nearby_restaurants(lat, lng, google_api_key)
            df = pd.DataFrame(restaurants)
            df = preprocess_restaurant_data(df)
            st.dataframe(df[['이름', '주소', '평점']].head(10))



            st.subheader("🗺 지도에서 보기")
            m = folium.Map(location=[lat, lng], zoom_start=13)
            folium.Marker([lat, lng], tooltip="관광지", icon=folium.Icon(color="blue")).add_to(m)
            
            for _, r in df.iterrows():
                    folium.Marker(
                        [r['위도'], r['경도']],
                        tooltip=f"{r['이름']} (⭐{r['평점']})",
                        icon=folium.Icon(color="green", icon="cutlery", prefix='fa')
                    ).add_to(m)

            st_folium(m, width=700, height=500)

            # CSV 다운로드
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 맛집 목록 CSV 다운로드",
                data=csv,
                file_name=f"{selected_place}_맛집목록.csv",
                mime='text/csv'
            )

if __name__ == "__main__":
    main()