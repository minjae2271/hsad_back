from flask import Flask, request, jsonify 
from dotenv import load_dotenv
import os
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
from openai import OpenAI
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.chat_models import ChatOpenAI

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
email = os.getenv("AMAZON_EMAIL")
password = os.getenv("AMAZON_PASSWORD")

app = Flask(__name__)

CORS(app)

def build_actual_response(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response

def engine():
    chrome_options = Options()
    chrome_options.binary_location = "/usr/bin/chrome" 
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument('--no-sandbox')
    # chrome_options.add_argument('--remote-debugging-port=9222')
    # chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def amazon_login(email, password, driver):
    base_url = "https://www.amazon.de/ap/signin"
    params = {
    "openid.pape.max_auth_age": "900",  # 최대 인증 허용 시간 (초 단위)
    "openid.return_to": "https://www.amazon.de",  # 인증 성공 후 리다이렉션 URL
    "openid.assoc_handle": "deflex",  # 사이트/서비스의 프로파일 핸들
    "openid.mode": "checkid_setup",  # OpenID 인증 요청 단계
    "openid.ns": "http://specs.openid.net/auth/2.0"  # OpenID 프로토콜 버전
    }
    
    url = base_url + "?" + "&".join([f"{key}={value}" for key, value in params.items()])
    try:
        driver.get(url)
        time.sleep(2)


        email_input = driver.find_element(By.ID, "ap_email")
        email_input.send_keys(email)

        # "Continue" 버튼 클릭
        driver.find_element(By.ID, "continue").click()
        time.sleep(2)

        # 비밀번호 입력
        password_input = driver.find_element(By.ID, "ap_password")
        password_input.send_keys(password)

        driver.find_element(By.ID, "signInSubmit").click()
        time.sleep(3)  
        
        if "your-account" in driver.current_url or "nav_youraccount_btn" in driver.page_source:
            print("로그인 성공!")

        else:
            print("로그인 실패. 자격 증명을 확인하세요.")

    except Exception as e:
        print(f"로그인 중 오류 발생: {e}")

def amazon_search(driver, search_query):
    search_query_encoded = search_query.replace(" ", "+")
    base_url = "https://www.amazon.de/s?k="
    full_url = f"{base_url}{search_query_encoded}"
    print(f"접속할 URL: {full_url}")

    driver.get(full_url)
    time.sleep(3)

def get_info(driver, search_query, how_many):
    asins = {}

    try:
        products = driver.find_elements(By.CSS_SELECTOR, '[data-component-type="s-search-result"]')[: how_many]
        print(f"{search_query}에 대한 제품 정보:")
        
        for i, product in enumerate(products, start=1):
            try:
                asin = product.get_attribute("data-asin")
                
                if asin in asins:
                    continue
                    
                asins[asin] = {}
                
                # 제품 이름 가져오기
                product_name = product.find_element(By.CSS_SELECTOR, "[data-cy='title-recipe'] > a > h2 > span").text
                asins[asin]["product_name"] = product_name
                print(f"product_name : {product_name}")

                # link = product_name.find_element(By.CSS_SELECTOR, "a")
                # href = link.get_attribute('href')
                # asins[asin]["href"] = href

                # 가격
                price_symbol = product.find_element(By.CSS_SELECTOR, "span.a-price-symbol").text
                price_whole = product.find_element(By.CSS_SELECTOR, "span.a-price-whole").text
                price_fraction = product.find_element(By.CSS_SELECTOR, "span.a-price-fraction").text
                full_price = price_whole + "." + price_fraction
                asins[asin]["price"] = price_symbol + " " + full_price
                print(f'Price : {price_symbol} {full_price}')
                print("------------------------------------------------------------------------->")

            except Exception as e:
                print(f"{i}. 정보를 가져오지 못했습니다. 오류: {e}")
        return asins
    except Exception as e:
        print("제품 정보를 가져오는 데 실패했습니다:", e)

def five_review_collect(driver, asin):   
    url = f"https://www.amazon.de/product-reviews/{asin}?ie=UTF8&filterByStar=five_star&reviewerType=all_reviews&pageNumber=1"
    de_review_list = []
    try:
        driver.execute_script(f"window.open('{url}', '_blank');")
        
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(2)

        reviews = driver.find_elements(By.CSS_SELECTOR, 'div#cm_cr-review_list > ul')
        de_reviews = reviews[0].find_elements(By.CSS_SELECTOR, 'li')

        for de_review in de_reviews:
            de_review_body = de_review.find_element(By.CSS_SELECTOR, "[data-hook='review-body']").text
            de_review_list.append(de_review_body)

        
    except Exception as e:
        print(f"에러 발생: {e}")
    finally:
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return de_review_list


def one_review_collect(driver, asin):
    url = f"https://www.amazon.de/product-reviews/{asin}?ie=UTF8&filterByStar=one_star&reviewerType=all_reviews&pageNumber=1"
    de_review_list = []
    try:
        driver.execute_script(f"window.open('{url}', '_blank');")
        
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(2)
        
        reviews = driver.find_elements(By.CSS_SELECTOR, 'div#cm_cr-review_list > ul')
        de_reviews = reviews[0].find_elements(By.CSS_SELECTOR, 'li')

        for de_review in de_reviews:
            de_review_body = de_review.find_element(By.CSS_SELECTOR, "[data-hook='review-body']").text
            de_review_list.append(de_review_body)

        # return de_review_list
        
    except Exception as e:
        print(f"에러 발생: {e}")
    finally:
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return de_review_list

# def get_review_summary(review_text):
#     print("text", review_text)
#     try:        
#         chat = ChatOpenAI(openai_api_key=API_KEY)

#         response_schemas = [
#             ResponseSchema(
#                 name="summary",
#                 description="The summary of the review for the product."
#             ),
#         ]
#         output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
#         format_instructions = output_parser.get_format_instructions()
    
#         sysTemplate = """You are an advanced language model specializing in extracting insights and summarizing text. \
#         Your task is to analyze reviews and summarize common opinions concisely and accurately.\
#         The following is a series of reviews separated by '|'. \
#         Please read the reviews and summarize the common opinions and feelings in approximately 3 sentences. \
#         if there is no review, just return {'summary': 'No Reviews'} \
#         Use the reviews delimited by ####. \
#         review:####{review_text}#### \
#         {format_instructions}
#         """
#         system_message_prompt = SystemMessagePromptTemplate.from_template(sysTemplate)

#         humanTemplate = """
#         Please read the reviews and summarize them.
#         """
#         human_message_prompt = HumanMessagePromptTemplate.from_template(humanTemplate)

#         chat_prompt = ChatPromptTemplate(
#             messages=[system_message_prompt, human_message_prompt],
#             input_variables=["review_text"],
#             partial_variables={"format_instructions": format_instructions}
#         )
        
#         _input = chat_prompt.format_prompt(
#             review_text=review_text
#         )
#         output = chat(_input.to_messages())
#         print(f"outtttttttttttttttttttttttttttt{output_parser.parse(output.content)}")
#         return output_parser.parse(output.content)

#     except Exception as e:
#         print(f"Error while summarizing reviews: {e}")
#         return { "summary": "Error occurred"}

def get_review_summary(review_text, product_name, review_type):
    # if review_text == "No Review":
    #     output = {"product_name": product_name, "summary": "No Reviews"}
    #     print(output)
    #     return output
    try:        
        chat = ChatOpenAI(openai_api_key=API_KEY)

        response_schemas = [
            ResponseSchema(
                name="product_name",
                description="The name of the product."
            ),
            ResponseSchema(
                name="summary",
                description="The summary of the review for the product."
            ),
        ]
        output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
        format_instructions = output_parser.get_format_instructions()
    
        sysTemplate = """You are an advanced language model specializing in extracting insights and summarizing text. \
        Your task is to analyze reviews and summarize common opinions concisely and accurately.\
        The following is a series of reviews separated by '|'. \
        Please read the reviews and summarize the common opinions and feelings in approximately 3 sentences. \
        Use the product_name and reviews delimited by ####. \
        product_name:####{product_name}#### \
        review:####{review_text}#### \
        {format_instructions}
        """
        system_message_prompt = SystemMessagePromptTemplate.from_template(sysTemplate)

        humanTemplate = """
        Please read the reviews and summarize them.
        """
        human_message_prompt = HumanMessagePromptTemplate.from_template(humanTemplate)

        chat_prompt = ChatPromptTemplate(
            messages=[system_message_prompt, human_message_prompt],
            input_variables=["product_name", "review_text"],
            partial_variables={"format_instructions": format_instructions}
        )
        
        _input = chat_prompt.format_prompt(
            review_text=review_text, product_name=product_name
        )
        output = chat(_input.to_messages())
        print(output_parser.parse(output.content))
        return output_parser.parse(output.content)

    except Exception as e:
        print(f"Error while summarizing {review_type} reviews: {e}")
        return {"product_name": product_name, "summary": "Error occurred"}
    finally:
        print("--------------------------------------------------------")

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route("/search", methods=["GET"])
def search():
    try:
        if request.method == 'GET':
            search_query = request.args.get('search_query')
            how_many = int(request.args.get('how_many'))
        
        # print(search_query)
        # print(how_many)

        driver = engine()

        amazon_login(email, password, driver)
        amazon_search(driver, search_query)

        asins = get_info(driver, search_query, how_many)

        for asin in asins.keys():
            asins[asin]["five_reviews"] =  five_review_collect(driver, asin)
            asins[asin]["one_reviews"] = one_review_collect(driver, asin)

        driver.quit()

        return jsonify(asins)

    except Exception as e:
        return {"message": f"Server Error: {e}"}

@app.route("/summary", methods=["POST"])
def summary():
    try:
        if request.method == 'POST':
            print('om!')
            asins = request.get_json()
        # print(f"asins: {asins}")

        for asin, info in asins.items():
            print('im!')
            print("-------------------------------")
            # print(get_review_summary("|".join(info["five_reviews"])))

            asins[asin]["five_star_summary"] = get_review_summary("|".join(info["five_reviews"]), info["product_name"], "five-star")
            asins[asin]["one_star_summary"] = get_review_summary("|".join(info["one_reviews"]), info["product_name"], "one-star")
        
        return jsonify(asins)

    except Exception as e:
        return {"message": e}

if __name__ == "__main__":
    app.run(debug=True)