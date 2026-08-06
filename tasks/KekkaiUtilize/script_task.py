# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import re
import time
from cached_property import cached_property
from datetime import timedelta, datetime

from module.base.timer import Timer
from module.atom.image_grid import ImageGrid
from module.logger import logger
from module.exception import TaskEnd

from tasks.GameUi.game_ui import GameUi
from tasks.Utils.config_enum import ShikigamiClass
from tasks.KekkaiUtilize.assets import KekkaiUtilizeAssets
from tasks.KekkaiUtilize.config import UtilizeRule, SelectFriendList
from tasks.KekkaiUtilize.utils import CardClass, target_to_card_class
from tasks.Component.ReplaceShikigami.replace_shikigami import ReplaceShikigami
from tasks.GameUi.page import page_main, page_guild
from module.base.utils import point2str
import random

""" 结界蹭卡 """


class ScriptTask(GameUi, ReplaceShikigami, KekkaiUtilizeAssets):
    last_best_index = 99
    utilize_add_count = 0
    ap_max_num = 0
    jade_max_num = 0
    moon_max_num = 0
    first_utilize = True

    def run(self):
        con = self.config.kekkai_utilize.utilize_config
        self.ui_get_current_page()
        self.ui_goto(page_guild)

        # 进入寮结界
        self.goto_realm()
        # 育成界面去蹭卡
        if con.utilize_enable:
            self.check_utilize_add()

        # 查看育成满级
        self.check_max_lv(con.shikigami_class)
        # 检查蹭卡收获
        self.check_utilize_harvest()
        # 收体力盒子或者是经验盒子
        self.check_box_ap_or_exp(con.box_ap_enable, con.box_exp_enable, con.box_exp_waste)

        # 收取寮资金和体力
        self.recive_guild_ap_or_assets(con.harvest_guild_max_times)
        if not con.utilize_enable:
            self.set_next_run(task='KekkaiUtilize', finish=True, success=True)
        raise TaskEnd

    def recive_guild_ap_or_assets(self, max_tries: int = 3):
        for i in range(1, max_tries+1):
            self.ui_get_current_page()
            self.ui_goto(page_guild)
            # 在寮的主界面 检查是否有收取体力或者是收取寮资金
            if self.check_guild_ap_or_assets():
                logger.warning(f'第[{i}]次检查寮收获,成功')
                self.ui_goto(page_main)
                break
            else:
                logger.warning(f'第[{i}]次检查寮收获寮收获,失败')
            self.ui_goto(page_main)

    def check_utilize_add(self):
        con = self.config.kekkai_utilize.utilize_config
        while 1:
            self.utilize_add_count += 1
            if self.utilize_add_count >= 5:
                logger.warning('没有合适可以蹭的卡, 5分钟后再次执行蹭卡')
                self.push_notify(content=f"没有合适可以蹭的卡, 5分钟后再次执行蹭卡")
                self.set_next_run(task='KekkaiUtilize', target=datetime.now() + timedelta(minutes=5))
                return

            # 无论收不收到菜，都会进入看看至少看一眼时间还剩多少
            time.sleep(0.5)
            # 进入育成界面
            self.realm_goto_grown()
            self.screenshot()

            if not self.appear(self.I_UTILIZE_ADD):
                remaining_time = self.O_UTILIZE_RES_TIME.ocr(self.device.image)
                if not isinstance(remaining_time, timedelta):
                    logger.warning('Ocr remaining time error')
                logger.info(f'Utilize remaining time: {remaining_time}')
                # 已经蹭上卡了，设置下次蹭卡时间  # 减少30秒
                # remaining_time = remaining_time - timedelta(seconds=30)
                if remaining_time and remaining_time > timedelta(0):
                    next_time = datetime.now() + remaining_time
                    self.set_next_run(task='KekkaiUtilize', target=next_time)
                else:
                    logger.warning('Utilize remaining time is zero, use normal schedule')
                    self.set_next_run(task='KekkaiUtilize', finish=True, success=True)
                return
            if not self.grown_goto_utilize():
                logger.info('Utilize failed, exit')
            # 开始执行寄养
            if self.run_utilize(con.select_friend_list, con.shikigami_class, con.shikigami_order):
                # 退出寮结界
                self.back_guild()
                # 进入寮结界
                self.goto_realm()
            else:
                self.back_realm()

    def check_max_lv(self, shikigami_class: ShikigamiClass = ShikigamiClass.N):
        """
        在结界界面，进入式神育成，检查是否有满级的，如果有就换下一个
        退出的时候还是结界界面
        :return:
        """
        self.realm_goto_grown()
        if self.appear(self.I_RS_LEVEL_MAX):
            # 存在满级的式神
            logger.info('Exist max level shikigami and replace it')
            self.unset_shikigami_max_lv()
            self.switch_shikigami_class(shikigami_class)
            self.set_shikigami(shikigami_order=7, stop_image=self.I_RS_NO_ADD)
        else:
            logger.info('No max level shikigami')
        if self.detect_no_shikigami():
            logger.warning('There are no any shikigami grow room')
            self.switch_shikigami_class(shikigami_class)
            self.set_shikigami(shikigami_order=7, stop_image=self.I_RS_NO_ADD)

        # 回到结界界面
        while 1:
            self.screenshot()

            if self.appear(self.I_REALM_SHIN) and self.appear_multi_scale(self.I_SHI_GROWN):
                self.screenshot()
                if not self.appear(self.I_REALM_SHIN):
                    continue
                break
            if self.appear_then_click(self.I_UI_BACK_BLUE, interval=2.5):
                continue

    def check_guild_ap_or_assets(self, ap_enable: bool = True, assets_enable: bool = True) -> bool:
        """
        在寮的主界面 检查是否有收取体力或者是收取寮资金
        如果有就顺带收取
        :return:
        """
        timer_check = Timer(2)
        timer_check.start()
        click_ap = False
        while 1:
            self.screenshot()

            # 获得奖励
            if self.ui_reward_appear_click():
                timer_check.reset()
                continue

            if timer_check.reached():
                return False

            if click_ap and not self.appear(self.I_GUILD_AP) and not self.appear(self.I_UI_REWARD):
                return True

            # 关闭展开的寮活动横幅
            if self.appear_then_click(self.I_GUILD_EXPAND):
                timer_check.reset()
                continue

            # 资金收取确认
            if self.appear_then_click(self.I_GUILD_ASSETS_RECEIVE, interval=1):
                time.sleep(1)
                timer_check.reset()
                continue

            # 收资金
            if self.appear_then_click(self.I_GUILD_ASSETS, interval=1.5, threshold=0.6):
                timer_check.reset()
                continue

            # 收体力
            if self.appear_then_click(self.I_GUILD_AP, interval=1):
                # 等待1秒，看到获得奖励
                time.sleep(1)
                logger.info('appear_click guild_ap success')
                if self.ui_reward_appear_click(True):
                    logger.info('appear_click reward success')
                    click_ap = True
                    timer_check.reset()
                continue

    def goto_realm(self):
        """
        从寮的主界面进入寮结界
        :return:
        """
        while 1:
            self.screenshot()
            if self.appear(self.I_REALM_SHIN):
                break
            if self.appear_multi_scale(self.I_SHI_DEFENSE):
                break
            if self.appear_then_click(self.I_PLANT_TREE_CLOSE):
                continue
            if self.appear_then_click(self.I_GUILD_REALM, interval=1):
                continue

    def check_box_ap_or_exp(self, ap_enable: bool = True, exp_enable: bool = True, exp_waste: bool = True) -> bool:
        """
        顺路检查盒子
        :param ap_enable:
        :param exp_enable:
        :return:
        """

        # 退出到寮结界
        def _exit_to_realm():
            # 右上方关闭红色
            while 1:
                self.screenshot()
                if self.appear(self.I_REALM_SHIN):
                    break
                if self.appear_then_click(self.I_UI_BACK_RED, interval=1):
                    continue

        # 先是体力盒子
        def _check_ap_box(appear: bool = False):
            if not appear:
                return False
            # 点击盒子
            timer_ap = Timer(6)
            timer_ap.start()
            while 1:
                self.screenshot()

                if self.appear(self.I_UI_REWARD):
                    while 1:
                        self.screenshot()
                        if not self.appear(self.I_UI_REWARD):
                            break
                        if self.appear_then_click(self.I_UI_REWARD, self.C_UI_REWARD, interval=1, threshold=0.6):
                            continue
                    logger.info('Reward box')
                    break

                if self.appear_then_click(self.I_BOX_AP, interval=1):
                    continue
                if self.appear_then_click(self.I_AP_EXTRACT, interval=2):
                    continue
                if timer_ap.reached():
                    logger.warning('Extract ap box timeout')
                    break
            logger.info('Extract AP box finished')
            _exit_to_realm()

        # 经验盒子
        def _check_exp_box(appear: bool = False):
            if not appear:
                logger.info('No exp box')
                return False

            time_exp = Timer(12)
            time_exp.start()
            while 1:
                self.screenshot()
                # 如果出现结界皮肤， 表示收取好了
                if self.appear(self.I_REALM_SHIN) and not self.appear(self.I_BOX_EXP, threshold=0.6):
                    break
                # 如果出现收取确认，表明进入到了有满级的
                if self.appear(self.I_UI_CONFIRM):
                    self.screenshot()
                    if not self.appear(self.I_UI_CANCEL):
                        logger.info('No cancel button')
                        continue
                    if exp_waste:
                        check_button = self.I_UI_CONFIRM
                    else:
                        check_button = self.I_UI_CANCEL
                    while 1:
                        self.screenshot()
                        if not self.appear(check_button):
                            break
                        if self.appear_then_click(check_button, interval=1):
                            continue
                    break

                if self.appear(self.I_EXP_EXTRACT):
                    # 如果达到今日领取的最大，就不领取了
                    cur, res, totol = self.O_BOX_EXP.ocr(self.device.image)
                    if cur == res == totol == 0:
                        continue
                    if cur == totol and cur + res == totol:
                        logger.info('Exp box reach max do not collect')
                        break
                if self.appear_then_click(self.I_BOX_EXP, threshold=0.6, interval=1):
                    continue
                if self.appear_then_click(self.I_EXP_EXTRACT, interval=1):
                    continue

                if time_exp.reached():
                    logger.warning('Extract exp box timeout')
                    break
            _exit_to_realm()

        self.screenshot()
        box_ap = self.appear(self.I_BOX_AP)
        box_exp = self.appear(self.I_BOX_EXP, threshold=0.6) or self.appear(self.I_BOX_EXP_MAX, threshold=0.6)
        if ap_enable:
            _check_ap_box(box_ap)
        if exp_enable:
            _check_exp_box(box_exp)

    def check_utilize_harvest(self) -> bool:
        """
        在寮结界界面检查是否有收获
        :return: 如果没有返回False, 如果有就收菜返回True
        """
        self.screenshot()
        appear = self.appear(self.I_UTILIZE_EXP)
        if not appear:
            logger.info('No utilize harvest')
            return False

        # 收获
        self.ui_get_reward(self.I_UTILIZE_EXP)
        return True

    def realm_goto_grown(self):
        """
        进入式神育成界面
        :return:
        """
        while 1:
            self.screenshot()

            if self.in_shikigami_growth():
                break

            if self.appear_then_click_multi_scale(self.I_SHI_GROWN, interval=1):
                continue
        logger.info('Enter shikigami grown')

    def grown_goto_utilize(self):
        """
        从式神育成界面到 蹭卡界面
        :return:
        """
        self.screenshot()
        if not self.appear(self.I_UTILIZE_ADD):
            logger.warning('No utilize add')
            return False

        while 1:
            self.screenshot()

            if self.appear(self.I_U_ENTER_REALM):
                break
            if self.appear_then_click(self.I_UTILIZE_ADD, interval=2):
                continue
        logger.info('Enter utilize')
        return True

    def switch_friend_list(self, friend: SelectFriendList = SelectFriendList.SAME_SERVER) -> bool:
        """
        切换不同的服务区
        :param friend:
        :return:
        """
        logger.info('Switch friend list to %s', friend)
        if friend == SelectFriendList.SAME_SERVER:
            check_image = self.I_UTILIZE_FRIEND_GROUP
        else:
            check_image = self.I_UTILIZE_ZONES_GROUP

        timer_click = Timer(1)
        timer_click.start()
        while 1:
            self.screenshot()
            if self.appear(check_image):
                break
            if timer_click.reached():
                timer_click.reset()
                x, y = check_image.coord()
                self.device.click(x=x, y=y, control_name=check_image.name)
        if friend == SelectFriendList.DIFFERENT_SERVER:
            time.sleep(1)
        time.sleep(0.5)

    @cached_property
    def order_targets(self) -> ImageGrid:
        rule = self.config.kekkai_utilize.utilize_config.utilize_rule
        if rule == UtilizeRule.DEFAULT:
            return ImageGrid([self.I_U_TAIKO_6, self.I_U_FISH_6, self.I_U_TAIKO_5, self.I_U_FISH_5,
                              self.I_U_TAIKO_4, self.I_U_FISH_4, self.I_U_TAIKO_3, self.I_U_FISH_3,
                              self.I_U_MOON_6, self.I_U_MOON_5, self.I_U_MOON_4, self.I_U_MOON_3,
                              self.I_U_MOON_2])
        elif rule == UtilizeRule.FISH:
            return ImageGrid([self.I_U_FISH_6, self.I_U_FISH_5])
        elif rule == UtilizeRule.TAIKO:
            return ImageGrid([self.I_U_TAIKO_6, self.I_U_TAIKO_5])
        else:
            logger.error('Unknown utilize rule')
            raise ValueError('Unknown utilize rule')

    @cached_property
    def order_cards(self) -> list[CardClass]:
        rule = self.config.kekkai_utilize.utilize_config.utilize_rule
        result = []
        if rule == UtilizeRule.DEFAULT:
            result = [CardClass.TAIKO6, CardClass.FISH6, CardClass.TAIKO5, CardClass.FISH5,
                      CardClass.TAIKO4, CardClass.FISH4, CardClass.TAIKO3, CardClass.FISH3,
                      CardClass.MOON6, CardClass.MOON5, CardClass.MOON4, CardClass.MOON3, CardClass.MOON2]
        elif rule == UtilizeRule.FISH:
            result = [CardClass.FISH6, CardClass.FISH5,
                      CardClass.TAIKO6, CardClass.TAIKO5, CardClass.FISH4, CardClass.TAIKO4, CardClass.FISH3,
                      CardClass.TAIKO3]
        elif rule == UtilizeRule.TAIKO:
            result = [CardClass.TAIKO6, CardClass.TAIKO5,
                      CardClass.FISH6, CardClass.FISH5, CardClass.TAIKO4, CardClass.FISH4, CardClass.TAIKO3,
                      CardClass.FISH3]
        else:
            logger.error('Unknown utilize rule')
            raise ValueError('Unknown utilize rule')
        return result

    def run_utilize(self, friend: SelectFriendList = SelectFriendList.SAME_SERVER,
                    shikigami_class: ShikigamiClass = ShikigamiClass.N,
                    shikigami_order: int = 7):
        """
        执行寄养
        :param shikigami_class:
        :param friend:
        :param rule:
        :return:
        """
        logger.hr('Start utilize')
        if self.first_utilize:
            self.swipe(self.S_U_END, interval=3)
            self.first_utilize = False
            if friend == SelectFriendList.SAME_SERVER:
                self.switch_friend_list(SelectFriendList.DIFFERENT_SERVER)
                self.switch_friend_list(SelectFriendList.SAME_SERVER)
            else:
                self.switch_friend_list(SelectFriendList.SAME_SERVER)
                self.switch_friend_list(SelectFriendList.DIFFERENT_SERVER)
        else:
            self.switch_friend_list(friend)

        # --------------- 结界卡选择 ---------------
        if not self._select_optimal_resource_card():
            return False

        # 找到卡,重置次数
        self.utilize_add_count = 0
        logger.info('开始执行进入结界蹭卡流程')
        self.screenshot()
        # 进入结界
        if not self.appear(self.I_U_ENTER_REALM):
            logger.warning('Cannot find enter realm button')
            # 可能是滑动的时候出错
            logger.warning('The best reason is that the swipe is wrong')
            return
        wait_timer = Timer(20)
        wait_timer.start()
        while 1:
            self.screenshot()
            # 有空位：点进入结界后直接弹出式神放置面板（人间烟火气的结界/可放置式神寄养）
            if self.appear(self.I_U_REALM_PICKER):
                logger.info('Appear shikigami picker (friend realm has free slot)')
                break
            # 无坑位：进入好友结界视图（结界防守/式神育成/结界卡）
            if self.appear(self.I_SHI_CARD) or self.appear(self.I_SHI_DEFENSE):
                logger.info('Appear friend realm view (no free slot)')
                break
            if wait_timer.reached():
                self.save_image(wait_time=0, push_flag=False, content='进入好友结界超时', image_type='png')
                logger.warning('Appear friend realm timeout')
                return
            # 还在借卡界面/加载中，继续点击进入结界
            if self.appear_then_click(self.I_CHECK_FRIEND_REALM_2, interval=1.5):
                logger.info('Click too fast to enter the friend\'s realm pool')
                continue
            if self.appear_then_click(self.I_U_ENTER_REALM, interval=2.5):
                time.sleep(0.5)
                continue

        # 无坑位（好友结界已满）
        if self.appear(self.I_SHI_CARD) or self.appear(self.I_SHI_DEFENSE):
            self.save_image(content='没有坑位了', wait_time=0, push_flag=False, image_type='png')
            logger.warning('没有坑位可能是其他人的手速太快了抢占了')
            return True

        logger.info('Enter friend realm, place shikigami')
        # 在好友结界的式神放置面板中选择并放入式神
        return self._place_shikigami_in_picker(shikigami_order)

    def _place_shikigami_in_picker(self, shikigami_order: int = 7) -> bool:
        """
        在好友结界的式神放置面板中放入式神
        流程: 点式神格子 -> 弹出确认框 -> 点确定 -> 面板关闭即放置成功
        注: 好友放置面板没有 N/R/SR/SSR 等分类切换，直接按格子序号选择
        :param shikigami_order: 式神格子序号 1-8
        :return:
        """
        click_match = {1: self.C_SHIKIGAMI_LEFT_1, 2: self.C_SHIKIGAMI_LEFT_2,
                       3: self.C_SHIKIGAMI_LEFT_3, 4: self.C_SHIKIGAMI_LEFT_4,
                       5: self.C_SHIKIGAMI_LEFT_5, 6: self.C_SHIKIGAMI_LEFT_6,
                       7: self.C_SHIKIGAMI_LEFT_7, 8: self.C_SHIKIGAMI_LEFT_8}
        # 主选配置的格子，弹不出确认框时依次尝试相邻格子（可能已被占坑）
        order_list = [shikigami_order]
        for delta in range(1, 8):
            if shikigami_order + delta <= 8:
                order_list.append(shikigami_order + delta)
            if shikigami_order - delta >= 1:
                order_list.append(shikigami_order - delta)

        timer = Timer(60)
        timer.start()
        tap_timer = Timer(2.0).start()
        clicked_confirm = False
        pos_index = 0
        while 1:
            self.screenshot()
            # 出现确认框 -> 点确定
            if self.appear(self.I_U_REALM_CONFIRM):
                self.click(self.C_U_REALM_CONFIRM, interval=1)
                clicked_confirm = True
                logger.info('Click confirm to place shikigami')
                time.sleep(1)
                continue
            # 确认后面板关闭 -> 放置成功
            if clicked_confirm and not self.appear(self.I_U_REALM_PICKER):
                logger.info('Shikigami picker closed, placement done')
                return True
            # 面板还在且无确认框 -> 点式神格子
            if not clicked_confirm and tap_timer.reached_and_reset():
                pos = order_list[pos_index % len(order_list)]
                pos_index += 1
                self.click(click_match[pos], interval=1)
                logger.info('Tap shikigami slot %d' % pos)
            if timer.reached():
                if clicked_confirm:
                    logger.warning('Place shikigami confirm timeout, assume done')
                    return True
                logger.warning('Place shikigami in friend realm timeout')
                self.save_image(content='放置式神超时', wait_time=0, push_flag=False, image_type='png')
                return False

    def _select_optimal_resource_card(self):
        """智能选卡主逻辑：按寄养规则优先级（太鼓6>斗鱼6>太鼓5>斗鱼5>太鼓4>斗鱼4>太鼓3>斗鱼3>太阴）选择最佳结界卡"""
        logger.hr('第一阶段：初始记录获取', 2)
        best_rank, best_value = self._explore_record()
        if best_rank is None:
            logger.warning('❌ 没有找到任何合适的结界卡')
            self.ap_max_num, self.jade_max_num, self.moon_max_num = 0, 0, 0
            return False
        logger.info(f'📝 最佳结界卡 | 排名:{best_rank} 数值:{best_value}')

        # 重置好友列表到顶部后重新确认选择
        self._reset_friend_list()

        logger.hr('第二阶段：执行选卡', 2)
        if self._confirm_select(best_rank):
            logger.info('✅ 蹭卡确认成功，重置状态')
            self.ap_max_num, self.jade_max_num, self.moon_max_num = 0, 0, 0
            return True
        logger.warning('❌ 蹭卡确认失败，重置状态')
        self.ap_max_num, self.jade_max_num, self.moon_max_num = 0, 0, 0
        return False

    @staticmethod
    def _card_rank(target) -> int:
        """根据匹配到的模板计算卡片优先级排名（越小越优先）
        太鼓6→1 斗鱼6→2 太鼓5→3 斗鱼5→4 太鼓4→5 斗鱼4→6 太鼓3→7 斗鱼3→8 太阴6→9 ...
        """
        name = target.name
        try:
            tier = int(name.rsplit('_', 1)[-1])
        except (ValueError, IndexError):
            return 99
        if 'TAIKO' in name:
            return (6 - tier) * 2 + 1
        if 'FISH' in name:
            return (6 - tier) * 2 + 2
        if 'MOON' in name:
            return 9 + (6 - tier)
        return 99

    @staticmethod
    def _rank_type(target) -> str:
        name = target.name
        if 'TAIKO' in name:
            return '太鼓'
        if 'FISH' in name:
            return '斗鱼'
        if 'MOON' in name:
            return '太阴'
        return 'unknown'

    def _reset_friend_list(self):
        """通过切换区服重置好友列表到顶部"""
        logger.info('重置好友列表到顶部')
        self.switch_friend_list(SelectFriendList.DIFFERENT_SERVER)
        self.switch_friend_list(SelectFriendList.SAME_SERVER)

    def _explore_record(self):
        """探索模式：扫描好友列表记录最佳结界卡
        :return: (best_rank, best_value)；未找到返回 (None, 0)
        """
        MAX_SWIPES = 20  # 最大滑动次数
        CONSEC_MISS = 3  # 允许连续无卡次数
        TIMEOUT = 120  # 操作超时(秒)
        logger.info('启动探索模式')
        timer = Timer(TIMEOUT).start()
        miss_count = 0
        best_rank, best_value = None, 0
        self.ap_max_num, self.jade_max_num, self.moon_max_num = 0, 0, 0
        record_attr_map = {'太鼓': 'jade_max_num', '斗鱼': 'ap_max_num', '太阴': 'moon_max_num'}

        for swipe_count in range(MAX_SWIPES + 1):
            # 超时检测
            if timer.reached():
                logger.warning('⏰ 操作超时，终止探索')
                break

            # 截图识别结界卡
            self.screenshot()
            cards = self.order_targets.find_everyone(self.device.image)

            # 处理无卡情况
            if not cards:
                miss_count += 1
                logger.info(f'第{swipe_count}次滑动 | 未检测到结界卡' if swipe_count > 0 else '初始界面 | 未检测到结界卡')
                if miss_count > CONSEC_MISS:
                    logger.warning(f'⚠️ 连续{miss_count}次 | 未检测到结界卡, 终止探索')
                    break
                self.perform_swipe_action()
                continue

            miss_count = 0
            for target, _, area in cards:
                # 点击结界卡获取详情
                self.C_SELECT_CARD.roi_front = area
                self.click(self.C_SELECT_CARD)
                time.sleep(2)

                # 解析结界卡类型和数值
                card_type, card_value = self.check_card_num()

                # 跳过无效结界卡
                if card_type == 'unknown' or card_value <= 0:
                    logger.info(f'⏭️ 跳过无效卡: {card_type}@{card_value}')
                    continue
                # 模板与OCR类型校验
                expected = self._rank_type(target)
                if card_type != expected:
                    logger.info(f'⏭️ 模板/OCR类型不匹配: 模板:{expected} OCR:{card_type}，跳过')
                    continue

                rank = self._card_rank(target)
                attr = record_attr_map.get(card_type)
                if attr and card_value > getattr(self, attr, 0):
                    setattr(self, attr, card_value)
                if best_rank is None or rank < best_rank or (rank == best_rank and card_value > best_value):
                    best_rank, best_value = rank, card_value
                    logger.info(f'📈 更新最佳卡 | 排名:{rank} 类型:{card_type} 数值:{card_value}')

            self.perform_swipe_action()

        if best_rank is None:
            logger.warning('❌ 未找到任何合适的结界卡')
            return None, 0
        logger.info(f'📝 探索完成 | 最佳排名:{best_rank} 数值:{best_value}')
        return best_rank, best_value

    def _confirm_select(self, best_rank):
        """确认模式：扫描好友列表选择排名不劣于 best_rank 的结界卡并蹭卡
        :param best_rank: 探索得到的最佳排名
        :return: 选择成功返回 True
        """
        MAX_SWIPES = 20
        CONSEC_MISS = 3
        TIMEOUT = 120
        logger.info(f'启动确认模式 | 目标排名: {best_rank}')
        timer = Timer(TIMEOUT).start()
        miss_count = 0

        for swipe_count in range(MAX_SWIPES + 1):
            if timer.reached():
                logger.warning('⏰ 操作超时，终止确认')
                return False
            self.screenshot()
            cards = self.order_targets.find_everyone(self.device.image)

            if not cards:
                miss_count += 1
                if miss_count > CONSEC_MISS:
                    logger.warning(f'⚠️ 连续{miss_count}次 | 未检测到结界卡, 终止确认')
                    return False
                self.perform_swipe_action()
                continue

            miss_count = 0
            for target, _, area in cards:
                self.C_SELECT_CARD.roi_front = area
                self.click(self.C_SELECT_CARD)
                time.sleep(2)
                card_type, card_value = self.check_card_num()

                if card_type == 'unknown' or card_value <= 0:
                    continue
                expected = self._rank_type(target)
                if card_type != expected:
                    continue
                rank = self._card_rank(target)
                if rank <= best_rank:
                    logger.info(f'🎉 确认蹭卡: 排名:{rank} 类型:{card_type} 数值:{card_value}')
                    self.save_image(push_flag=False, wait_time=0, content=f'🎉 确认蹭卡（{card_type}: {card_value}）')
                    return True

            self.perform_swipe_action()

        logger.warning('⚠️ 已达到最大滑动次数, 终止确认')
        return False


    def perform_swipe_action(self):
        """统一滑动操作"""
        duration = 2
        safe_pos_x = random.randint(340, 600)
        safe_pos_y = random.randint(500, 565)
        p1 = (safe_pos_x, safe_pos_y)
        p2 = (safe_pos_x, safe_pos_y - 416)
        logger.info('Swipe %s -> %s, %sS ' % (point2str(*p1), point2str(*p2), duration))
        self.device.swipe_adb(p1, p2, duration=duration)

        # self.swipe(self.S_U_UP, duration=1, wait_up_time=1)
        self.device.click_record_clear()
        time.sleep(2)

    def check_card_num(self) -> tuple[str, int]:
        """优化版数值提取方法，返回结界卡类型及对应数值"""
        self.O_CARD_NUM.roi = (700, 330, 330, 110)
        self.O_CARD_NUM.area = (700, 330, 330, 110)
        self.screenshot()
        # OCR识别
        raw_text = self.O_CARD_NUM.detect_text(self.device.image)
        logger.info(f'OCR原始结果: {raw_text}')

        # 判断结界卡类型
        if any(c in raw_text for c in ['体', 'カ', '力']):
            card_type = '斗鱼'
        elif any(c in raw_text for c in ['勾', '玉']):
            card_type = '太鼓'
        elif any(c in raw_text for c in ['经', '验', '阴']):
            card_type = '太阴'
        else:
            logger.warning(f'结界卡类型识别失败，原始内容: {raw_text}')
            # self.push_notify(content=f'结界卡类型识别失败: {raw_text}')
            return 'unknown', 0  # 未知类型返回0

        # 提取纯数字部分（兼容带+号的情况，如+100）
        cleaned = re.sub(r'[^\d+]', '', raw_text)  # 保留数字和加号
        match = re.search(r'\d+', cleaned)  # 匹配连续数字

        try:
            value = int(match.group()) if match else 0
        except ValueError:
            logger.warning(f'数值转换异常，清理后文本: {cleaned}')
            value = 0

        if value <= 0:
            self.push_notify(content=f'数值异常: {raw_text} -> 解析值: {value}')
            return card_type, 0

        # logger.info(f'识别成功: 卡类型: {card_type}, 数值: {value}')
        return card_type, value

    def back_guild(self):
        """
        回到寮的界面
        :return:
        """
        while 1:
            self.screenshot()

            if self.appear(self.I_GUILD_INFO):
                break
            if self.appear(self.I_GUILD_REALM):
                break
            if self.appear_then_click(self.I_PLANT_TREE_CLOSE):
                continue

            if self.appear_then_click(self.I_UI_BACK_RED, interval=1):
                continue
            if self.appear_then_click(self.I_UI_BACK_BLUE, interval=1):
                continue
            if self.appear_then_click(self.I_UI_BACK_YELLOW, interval=1):
                continue

    def back_realm(self):
        # 回到寮结界
        while 1:
            self.screenshot()
            if self.appear(self.I_REALM_SHIN):
                break
            if self.appear_multi_scale(self.I_SHI_DEFENSE):
                break
            if self.appear_then_click(self.I_UI_BACK_RED, interval=1):
                continue
            if self.appear_then_click(self.I_UI_BACK_BLUE, interval=1):
                continue


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    c = Config('switch')
    d = Device(c)
    t = ScriptTask(c, d)
    for i in range(10):
        t.perform_swipe_action()
    t.recive_guild_ap_or_assets()
    # t.check_utilize_add()
    # t.check_card_num('勾玉', 67)
    # t.screenshot()
    # print(t.appear(t.I_BOX_EXP, threshold=0.6))
    # print(t.appear(t.I_BOX_EXP_MAX, threshold=0.6))