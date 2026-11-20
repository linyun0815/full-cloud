package cn.full.cloud.module.oa.dal.mysql.meetingroom;

import cn.full.cloud.framework.common.pojo.PageResult;
import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.framework.mybatis.core.util.SqlDialectUtils;
import cn.full.cloud.module.oa.controller.admin.meetingroom.vo.room.OaMeetingRoomPageReqVO;
import cn.full.cloud.module.oa.dal.dataobject.meetingroom.OaMeetingRoomDO;
import cn.full.cloud.module.oa.enums.meetingroom.OaMeetingRoomBookingScopeEnum;
import cn.full.cloud.module.oa.enums.meetingroom.OaMeetingRoomStatusEnum;
import org.apache.ibatis.annotations.Mapper;

import java.util.Collection;
import java.util.List;

/**
 * OA 会议室 Mapper
 *
 * @author 芋道源码
 */
@Mapper
public interface OaMeetingRoomMapper extends BaseMapperX<OaMeetingRoomDO> {

    default PageResult<OaMeetingRoomDO> selectPage(OaMeetingRoomPageReqVO reqVO, Collection<Long> managerIds, Long bookingUserId) {
        LambdaQueryWrapperX<OaMeetingRoomDO> query = new LambdaQueryWrapperX<OaMeetingRoomDO>()
                .likeIfPresent(OaMeetingRoomDO::getName, reqVO.getName())
                .likeIfPresent(OaMeetingRoomDO::getLocation, reqVO.getLocation())
                .eqIfPresent(OaMeetingRoomDO::getType, reqVO.getType())
                .eqIfPresent(OaMeetingRoomDO::getStatus, reqVO.getStatus())
                .inIfPresent(OaMeetingRoomDO::getManagerUserId, managerIds);
        query.orderByAsc(OaMeetingRoomDO::getSort).orderByDesc(OaMeetingRoomDO::getId);
        if (bookingUserId != null) {
            // 可预定范围在分页前过滤，保证总数和每页记录一致
            query.eq(OaMeetingRoomDO::getAllowBooking, true)
                    .eq(OaMeetingRoomDO::getStatus, OaMeetingRoomStatusEnum.NORMAL.getStatus())
                    .and(scope -> scope.eq(OaMeetingRoomDO::getBookingScope, OaMeetingRoomBookingScopeEnum.ALL.getScope())
                            .or(specified -> specified.eq(OaMeetingRoomDO::getBookingScope, OaMeetingRoomBookingScopeEnum.SPECIFIED.getScope())
                                    .apply(SqlDialectUtils.jsonArrayContains("booking_user_ids", false), bookingUserId.toString())));
        }
        return selectPage(reqVO, query);
    }

    default List<OaMeetingRoomDO> selectListByName(String name) {
        return selectList(new LambdaQueryWrapperX<OaMeetingRoomDO>().likeIfPresent(OaMeetingRoomDO::getName, name)
                .orderByAsc(OaMeetingRoomDO::getSort).orderByDesc(OaMeetingRoomDO::getId));
    }

}
