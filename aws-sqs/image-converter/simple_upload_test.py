import boto3
import os
import sys
import time
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# AWS 配置
AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

def get_aws_client(service_name):
    """
    創建 AWS 客戶端並處理 region 配置
    """
    try:
        return boto3.client(service_name, region_name=AWS_REGION)
    except Exception as e:
        print(f"AWS 客戶端初始化失敗: {e}")
        print(f"請確認 AWS 認證和 region 設定正確")
        print(f"當前使用的 region: {AWS_REGION}")
        return None

def get_stack_info():
    """
    從 CloudFormation 獲取實際的資源名稱
    """
    cf_client = get_aws_client('cloudformation')
    if not cf_client:
        return None
    
    try:
        response = cf_client.describe_stacks(StackName='image-converter')
        outputs = response['Stacks'][0]['Outputs']
        
        stack_info = {}
        for output in outputs:
            if output['OutputKey'] == 'ImageBucketName':
                stack_info['source_bucket'] = output['OutputValue']
            elif output['OutputKey'] == 'ConvertedImageBucketName':
                stack_info['destination_bucket'] = output['OutputValue']
            elif output['OutputKey'] == 'ImageProcessingQueueUrl':
                stack_info['queue_url'] = output['OutputValue']
                # 從 URL 提取隊列名稱
                stack_info['queue_name'] = output['OutputValue'].split('/')[-1]
                stack_info['dlq_name'] = stack_info['queue_name'].replace('-queue-', '-dlq-')
        
        return stack_info
    except Exception as e:
        print(f"無法獲取 CloudFormation stack 資訊: {e}")
        print("將使用預設名稱")
        return {
            'source_bucket': 'image-converter-image-bucket-dev',
            'destination_bucket': 'image-converter-converted-image-bucket-dev',
            'queue_name': 'image-converter-image-processing-queue-dev',
            'dlq_name': 'image-converter-image-processing-dlq-dev'
        }

def upload_image_to_bucket(file_path, bucket_name, s3_key, thread_id=None):
    """
    上傳圖片檔案到指定的 S3 bucket
    """
    try:
        s3_client = get_aws_client('s3')
        if not s3_client:
            return False, f"Thread {thread_id}: S3 客戶端初始化失敗"
        
        # 設定 Content-Type
        file_extension = Path(file_path).suffix.lower()
        content_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp'
        }
        content_type = content_type_map.get(file_extension, 'application/octet-stream')
        
        # 上傳檔案
        s3_client.upload_file(
            file_path,
            bucket_name,
            s3_key,
            ExtraArgs={
                'ContentType': content_type,
                'Metadata': {
                    'original-name': os.path.basename(file_path),
                    'upload-time': datetime.now().isoformat(),
                    'thread-id': str(thread_id) if thread_id else 'main'
                }
            }
        )
        
        return True, f"Thread {thread_id}: 成功上傳 {s3_key}"
        
    except Exception as e:
        return False, f"Thread {thread_id}: 上傳失敗 {s3_key} - {str(e)}"

def create_test_image(filename, image_id=1, corrupted=False):
    """
    創建測試用的圖片檔案
    """
    try:
        from PIL import Image, ImageDraw
        
        if corrupted:
            # 創建一個故意損壞的圖片檔案來測試錯誤處理
            with open(filename, 'wb') as f:
                f.write(b'fake image data that will cause processing errors')
            return filename
        
        # 創建不同大小和顏色的圖片來模擬真實情況
        sizes = [(800, 600), (1200, 900), (400, 300), (1600, 1200)]
        colors = ['lightblue', 'lightgreen', 'lightcoral', 'lightyellow', 'lightpink']
        
        size = sizes[image_id % len(sizes)]
        color = colors[image_id % len(colors)]
        
        img = Image.new('RGB', size, color=color)
        draw = ImageDraw.Draw(img)
        
        # 添加文字和圖形
        draw.text((50, 50), f"Test Image #{image_id}", fill='black')
        draw.text((50, 80), f"Size: {size[0]}x{size[1]}", fill='darkblue')
        draw.text((50, 110), f"Created: {datetime.now().strftime('%H:%M:%S')}", fill='black')
        
        # 添加一些圖形
        draw.rectangle([50, 150, 150, 250], outline='red', width=2)
        draw.ellipse([200, 150, 300, 250], outline='green', width=2)
        
        # 儲存圖片
        img.save(filename, quality=85)
        return filename
        
    except ImportError:
        print("錯誤: 需要安裝 Pillow 套件")
        print("執行: pip install Pillow")
        return None
    except Exception as e:
        print(f"創建測試圖片失敗: {e}")
        return None

def batch_upload_test(num_images=30, max_workers=10):
    """
    批量上傳測試圖片
    """
    print(f"批量上傳測試 - 準備上傳 {num_images} 張圖片")
    print("=" * 60)
    
    # 獲取實際的 bucket 名稱
    stack_info = get_stack_info()
    if not stack_info:
        print("無法獲取 AWS 資源資訊，測試終止")
        return 0, 0
    
    bucket_name = stack_info['source_bucket']
    print(f"目標 Bucket: {bucket_name}")
    
    # 創建測試圖片
    test_files = []
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("步驟 1: 創建測試圖片...")
    for i in range(num_images):
        # 每10張圖片中有1張故意損壞，用來測試錯誤處理
        corrupted = (i % 10 == 9)
        filename = f"test_image_{i+1:03d}.jpg"
        
        if corrupted:
            filename = f"test_corrupted_{i+1:03d}.jpg"
            
        file_path = create_test_image(filename, i+1, corrupted)
        if file_path:
            test_files.append((file_path, corrupted))
            if corrupted:
                print(f"  創建損壞測試檔案: {filename}")
            else:
                print(f"  創建測試檔案: {filename}")
    
    print(f"\n步驟 2: 開始批量上傳 (使用 {max_workers} 個併發執行緒)...")
    
    # 使用多執行緒同時上傳
    upload_results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        
        for i, (file_path, is_corrupted) in enumerate(test_files):
            s3_key = f"batch-test/{timestamp}/image_{i+1:03d}_{os.path.basename(file_path)}"
            future = executor.submit(upload_image_to_bucket, file_path, bucket_name, s3_key, i+1)
            futures.append(future)
        
        # 收集結果
        for future in as_completed(futures):
            success, message = future.result()
            upload_results.append((success, message))
            print(f"  {message}")
    
    # 統計結果
    successful_uploads = sum(1 for success, _ in upload_results if success)
    failed_uploads = len(upload_results) - successful_uploads
    
    print(f"\n步驟 3: 上傳結果統計")
    print(f"  成功上傳: {successful_uploads} 張")
    print(f"  失敗上傳: {failed_uploads} 張")
    print(f"  總計: {len(upload_results)} 張")
    
    # 清理本地檔案
    print(f"\n步驟 4: 清理本地測試檔案...")
    for file_path, _ in test_files:
        try:
            os.remove(file_path)
            print(f"  刪除: {file_path}")
        except Exception as e:
            print(f"  刪除失敗: {file_path} - {e}")
    
    print(f"\n測試完成!")
    print(f"圖片處理流程應該會自動啟動:")
    print(f"  S3 -> EventBridge -> SQS -> Lambda")
    print(f"\n建議等待 2-5 分鐘後檢查:")
    print(f"  1. SQS 隊列狀態")
    print(f"  2. Dead Letter Queue (DLQ)")
    print(f"  3. Lambda 函數日誌")
    print(f"  4. 轉換後的圖片")
    
    return successful_uploads, failed_uploads

def check_sqs_status():
    """
    檢查 SQS 隊列狀態
    """
    print(f"使用 AWS Region: {AWS_REGION}")
    
    sqs_client = get_aws_client('sqs')
    if not sqs_client:
        return
    
    # 獲取實際的隊列名稱
    stack_info = get_stack_info()
    if not stack_info:
        return
    
    main_queue_name = stack_info['queue_name']
    dlq_name = stack_info['dlq_name']
    
    print("SQS 隊列狀態:")
    print("-" * 40)
    
    # 獲取隊列 URL
    try:
        main_queue_response = sqs_client.get_queue_url(QueueName=main_queue_name)
        main_queue_url = main_queue_response['QueueUrl']
        
        # 獲取主隊列屬性
        main_attrs = sqs_client.get_queue_attributes(
            QueueUrl=main_queue_url,
            AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
        )
        
        visible_messages = main_attrs['Attributes'].get('ApproximateNumberOfMessages', '0')
        invisible_messages = main_attrs['Attributes'].get('ApproximateNumberOfMessagesNotVisible', '0')
        
        print(f"主隊列 ({main_queue_name}):")
        print(f"  可見消息數: {visible_messages}")
        print(f"  處理中消息數: {invisible_messages}")
        
    except Exception as e:
        print(f"無法獲取主隊列狀態: {e}")
    
    # DLQ 狀態
    try:
        dlq_response = sqs_client.get_queue_url(QueueName=dlq_name)
        dlq_url = dlq_response['QueueUrl']
        
        dlq_attrs = sqs_client.get_queue_attributes(
            QueueUrl=dlq_url,
            AttributeNames=['ApproximateNumberOfMessages']
        )
        
        dlq_messages = dlq_attrs['Attributes'].get('ApproximateNumberOfMessages', '0')
        print(f"\nDead Letter Queue ({dlq_name}):")
        print(f"  失敗消息數: {dlq_messages}")
        
        if int(dlq_messages) > 0:
            print(f"  ** 發現 {dlq_messages} 個失敗的消息在 DLQ 中 **")
            print(f"  這表示有圖片處理失敗，DLQ 正常運作")
        
    except Exception as e:
        print(f"無法獲取 DLQ 狀態: {e}")

def check_conversion_results():
    """
    檢查轉換結果
    """
    print(f"使用 AWS Region: {AWS_REGION}")
    
    s3_client = get_aws_client('s3')
    if not s3_client:
        return
    
    # 獲取實際的 bucket 名稱
    stack_info = get_stack_info()
    if not stack_info:
        return
    
    bucket_name = stack_info['destination_bucket']
    
    print("轉換結果:")
    print("-" * 40)
    print(f"檢查 Bucket: {bucket_name}")
    
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix='converted/'
        )
        
        if 'Contents' in response:
            print(f"找到 {len(response['Contents'])} 個轉換後的檔案:")
            
            # 按照檔案類型分組
            file_types = {}
            for obj in response['Contents']:
                file_ext = Path(obj['Key']).suffix
                if file_ext not in file_types:
                    file_types[file_ext] = []
                file_types[file_ext].append(obj)
            
            for file_type, files in file_types.items():
                total_size = sum(obj['Size'] for obj in files)
                print(f"  {file_type} 檔案: {len(files)} 個 (總大小: {total_size/1024:.1f} KB)")
                
        else:
            print("沒有找到轉換後的檔案")
            print("可能原因:")
            print("  1. 處理仍在進行中")
            print("  2. Lambda 函數發生錯誤")
            print("  3. 所有消息都進入了 DLQ")
            
    except Exception as e:
        print(f"檢查轉換結果時發生錯誤: {e}")

def main():
    print("Image Converter 大量測試工具")
    print("=" * 50)
    print(f"AWS Region: {AWS_REGION}")
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--check-sqs":
            check_sqs_status()
            return
        elif sys.argv[1] == "--check-results":
            check_conversion_results()
            return
        elif sys.argv[1] == "--check-all":
            check_sqs_status()
            print("\n")
            check_conversion_results()
            return
        elif sys.argv[1].isdigit():
            num_images = int(sys.argv[1])
        else:
            print("用法:")
            print("  python simple_upload_test.py [數量]     # 上傳指定數量的圖片")
            print("  python simple_upload_test.py --check-sqs       # 檢查 SQS 隊狀態")
            print("  python simple_upload_test.py --check-results   # 檢查轉換結果")
            print("  python simple_upload_test.py --check-all       # 檢查所有狀態")
            print(f"\n環境變數設定:")
            print(f"  set AWS_DEFAULT_REGION=us-east-1")
            print(f"  set AWS_ACCESS_KEY_ID=your_access_key")
            print(f"  set AWS_SECRET_ACCESS_KEY=your_secret_key")
            return
    else:
        num_images = 30
    
    print(f"準備進行大量測試 - {num_images} 張圖片")
    print("這個測試將:")
    print("1. 創建多張不同大小的測試圖片")
    print("2. 包含一些故意損壞的檔案來測試錯誤處理")
    print("3. 使用多執行緒同時上傳以增加負載")
    print("4. 觀察 SQS 和 DLQ 的運作情況")
    
    confirm = input(f"\n確定要開始測試嗎? (y/N): ")
    if confirm.lower() != 'y':
        print("測試取消")
        return
    
    # 執行批量上傳測試
    successful, failed = batch_upload_test(num_images)
    
    print(f"\n等待處理完成...")
    print(f"建議在 2-5 分鐘後執行以下命令檢查結果:")
    print(f"  python {sys.argv[0]} --check-all")

if __name__ == "__main__":
    main()