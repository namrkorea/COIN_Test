import requests
curr_ip = requests.get("https://api.ipify.org").text
st.write(f"현재 서버 IP: {curr_ip}") # 화면에 출력됨

