import requests

url = "https://tracking.ibt.uber.com/tracking/1/click/vOp6DN4n7gq4Hx3IAqziImfy-T6o_QfeU8Iq_00F5tHbSTj4ojOTUxBzukEKkbvW2nO-y57_rdXlhPS8yJ8JnhkrZAkUnGyvhTCdXytEgpTaa4xVsOPARKaS6A7pHqGJkHq_rG3Fhb8uxE6WSBbT0lZ87grI3AxferwojO0sX7Bv2OAXOb9FRbGaITnrtNf29NhckLHLgpq0IMxTmhBNLqmksnABImSRyIJzYdXPQZyr5wRvp5U0Pp_aNJXeCRvjuTSL1N01Y8SQbvBtzbVCrJzeg5Dxk7yNiWqMVmjWJmvIrP212TzUuaXoSo9tDsoU6rmgZtnF9ADWD-EEY484Cw=="
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
print(r.status_code, r.headers.get("content-type"), r.url)
open("test_receipt.pdf", "wb").write(r.content)
