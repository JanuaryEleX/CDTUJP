import asyncio
import random
from urllib.parse import urljoin
from playwright.async_api import async_playwright, Error, Page, Dialog

# 教务系统的基础URL
BASE_URL = "https://10.120.4.50"



async def extract_links_from_page(page: Page, all_links: list):
    """
    在当前页面遍历课程列表，找出“未提交”课程的评价链接，并添加到 all_links 列表中。
    """
    print("=" * 50)
    TABLE_SELECTOR = "table#dataList"
    print(f"🔍 正在当前页面上查找课程列表...")

    try:
        # 等待表格出现，增加超时时间
        await page.locator(TABLE_SELECTOR).wait_for(timeout=15000)
        print("   ✅ 成功找到课程列表！")
    except Error:
        print(f"❌ 错误：在页面上未找到课程列表 ('{TABLE_SELECTOR}')。")
        return

    rows = page.locator(f"{TABLE_SELECTOR} tbody tr")
    num_rows = await rows.count()
    if num_rows == 0:
        print("   当前页面没有课程数据。")
        return

    print(f"   当前页面找到 {num_rows} 门课程。")

    page_links_count = 0
    for i in range(num_rows):
        row = rows.nth(i)
        cells = row.locator("td")
        if await cells.count() < 9:
            print(f"   - 第 {i+1} 行数据不完整，跳过。")
            continue

        submitted_status_cell = cells.nth(7)
        # 确保能正确读取到文字
        if (await submitted_status_cell.inner_text(timeout=2000)).strip() == "否":
            course_name = (await cells.nth(2).inner_text()).strip()
            teacher_name = (await cells.nth(3).inner_text()).strip()
            evaluation_link_element = row.locator('a:has-text("评价")')

            if await evaluation_link_element.count() > 0:
                relative_link = await evaluation_link_element.get_attribute('href')
                full_link = urljoin(BASE_URL, relative_link)
                
                # 使用字典存储，方便后续使用
                link_info = {
                    "course": course_name,
                    "teacher": teacher_name,
                    "url": full_link
                }
                
                # 检查是否已存在（基于URL）
                if not any(d['url'] == full_link for d in all_links):
                    all_links.append(link_info)
                    page_links_count += 1

    print(f"   在本页新提取了 {page_links_count} 个链接。")

async def handle_dialog(dialog: Dialog):
    """自动处理弹窗"""
    print(f"✅ 捕获到弹窗 -> 类型: '{dialog.type}', 内容: '{dialog.message}'")
    await dialog.accept()
    print("   已自动点击'确定'。")

async def fill_evaluation_form(page: Page):
    """
    核心评教逻辑：填写表单、保存、提交。
    """
    print("   正在页面上查找评教表单...")

    try:
        # 等待第一个问题行出现，超时时间设置为10秒
        await page.wait_for_selector('//tr[.//td[@name="zbtd"]]', timeout=10000)
        print("   成功检测到评教表单。")
    except Exception:
        print("   ❌ 错误：在10秒内未找到评教表单。页面可能未正确加载或结构已改变。")
        return False

    # 1. 自动选择选项
    question_rows = page.locator('//tr[.//td[@name="zbtd"]]')
    num_questions = await question_rows.count()

    if num_questions == 0:
        print("   ⚠️ 警告：虽然检测到表单，但未找到具体的评分项。")
        return False

    print(f"   找到 {num_questions} 个评分项目。")
    b_option_index = random.randint(0, num_questions - 1)
    print(f"   策略：随机选择第 {b_option_index + 1} 个项目为 B，其余为 A。")

    for i in range(num_questions):
        row = question_rows.nth(i)
        try:
            if i == b_option_index:
                await row.locator('label.radio').nth(1).click()  # B选项
            else:
                await row.locator('label.radio').nth(0).click()  # A选项
        except Exception as click_error:
            print(f"   点击第 {i+1} 个选项时出错: {click_error}")
            continue

    print("   所有选项已填写。")
    await page.wait_for_timeout(500)

    # 2. 点击【保存】按钮
    try:
        print("   正在点击【保存】按钮...")
        await page.locator("#bc").click(timeout=5000)
    except Exception as e:
        print(f"   ❌ 错误：无法点击【保存】按钮。错误: {e}")
        return False

    # 3. 点击【提交】按钮
    try:
        print("   正在点击【提交】按钮...")
        await page.locator("#tj").click(timeout=5000)
    except Exception as e:
        print(f"   ❌ 错误：无法点击【提交】按钮。错误: {e}")
        return False

    await page.wait_for_timeout(2000)
    print("   ✅ 本课程评教流程执行完毕。")
    return True



async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--ignore-certificate-errors'])
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        await page.goto(f"{BASE_URL}/jsxsd/")
        
        print("=" * 50)
        print("🚀 浏览器已打开，请先手动完成登录。")
        input("   登录成功后，请回到此窗口按 Enter 键...")

        # --- 步骤 1: 抓取所有待评价链接 ---
        
        target_url = input("\n🔗 请粘贴【评教列表页面】的完整URL，然后按Enter：\n")
        if not target_url.strip():
            print("❌ 您没有输入URL，程序即将退出。")
            await browser.close()
            return
            
        print(f"\n好的，正在导航到您提供的链接...")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)

        all_found_links = []
        page_number = 1

        while True:
            print(f"\n--- 正在处理第 {page_number} 页 ---")
            await extract_links_from_page(page, all_found_links)
            
            NEXT_PAGE_BUTTON_SELECTOR = 'span:has(i.layui-icon-next)'
            DISABLED_CLASS = 'disabled'
            next_button = page.locator(NEXT_PAGE_BUTTON_SELECTOR)
            
            if await next_button.count() == 0:
                print("\n没有找到“下一页”按钮，已到达最后一页或页面结构特殊。")
                break
                
            button_class = await next_button.get_attribute('class') or ""
            if DISABLED_CLASS in button_class:
                print("\n“下一页”按钮已禁用，已到达最后一页。")
                break
            
            print("   ...点击“下一页”...")
            await next_button.click()
            await page.wait_for_load_state('networkidle', timeout=10000)
            page_number += 1
        
        # --- 步骤 2: 显示结果并请求用户确认 ---

        print("\n" + "#"*70)
        if not all_found_links:
            print("#    所有页面扫描完毕，没有找到任何需要评价的课程。程序即将退出。   #")
            print("#"*70)
            await browser.close()
            return
        
        print(f"#    扫描完毕！共找到 {len(all_found_links)} 个待评价的课程：")
        print("#" + "-"*68 + "#")
        for index, item in enumerate(all_found_links):
            print(f"#  {index+1}. 《{item['course']}》- {item['teacher']}")
        print("#"*70)

        confirmation = input("\n🤔 是否要自动对以上所有课程进行评价？(输入 'y' 或 'yes' 确认): ").lower().strip()
        if confirmation not in ['y', 'yes']:
            print("\n❌ 操作已取消。浏览器将保持打开，您可以手动操作或关闭。")
            return

        # --- 步骤 3: 执行自动评价 ---

        print("\n✅ 已确认。即将开始自动评教流程...")
        page.on("dialog", handle_dialog) # 在开始评教前，注册弹窗处理器

        for i, item in enumerate(all_found_links):
            link = item['url']
            course_name = item['course']
            teacher_name = item['teacher']
            
            try:
                print("-" * 50)
                print(f"[{i+1}/{len(all_found_links)}] 正在处理: 《{course_name}》- {teacher_name}")
                print(f"   导航至: {link[:60]}...")
                
                await page.goto(link, wait_until="domcontentloaded")
                await fill_evaluation_form(page)

            except Exception as e:
                print(f"❌ 处理《{course_name}》时发生严重错误: {e}")
                screenshot_path = f"playwright_error_screenshot_{i+1}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"   已保存错误截图: {screenshot_path}")
                input("   程序暂停。请手动处理当前页面，然后按Enter继续下一个链接...")

        print("\n" + "="*50)
        print("🎉🎉🎉 所有评教任务已处理完毕！")
        print("浏览器将保持打开状态以便您检查。您可以手动关闭浏览器。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n程序运行出现意外错误: {e}")
        input("按Enter键退出...")
