class GameInfo:
    def __init__(self, channel_id: int):
        self.competitor_time_list = {}
        self.competitor_status = {}
        self.start_time = int()
        self.player_list = []
        self.channel_id = channel_id
        self.question_list = []
        self.question_index_num = int()
        self.word_count = int()

    def add_player(self, member_id: int):
        self.player_list.append(member_id)
        self.competitor_time_list[member_id] = []
        self.competitor_status[member_id] = 'answering'

    def remove_player(self, member_id: int):
        self.player_list.remove(member_id)
        del self.competitor_time_list[member_id]
        del self.competitor_status[member_id]