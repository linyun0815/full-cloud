package cn.full.cloud.module.mes.dal.mysql.wm.salesnotice;

import cn.full.cloud.framework.common.pojo.PageResult;
import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.mes.controller.admin.wm.salesnotice.vo.line.MesWmSalesNoticeLinePageReqVO;
import cn.full.cloud.module.mes.dal.dataobject.wm.salesnotice.MesWmSalesNoticeLineDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

/**
 * MES 发货通知单行 Mapper
 */
@Mapper
public interface MesWmSalesNoticeLineMapper extends BaseMapperX<MesWmSalesNoticeLineDO> {

    default PageResult<MesWmSalesNoticeLineDO> selectPage(MesWmSalesNoticeLinePageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<MesWmSalesNoticeLineDO>()
                .eqIfPresent(MesWmSalesNoticeLineDO::getNoticeId, reqVO.getNoticeId())
                .orderByDesc(MesWmSalesNoticeLineDO::getId));
    }

    default List<MesWmSalesNoticeLineDO> selectListByNoticeId(Long noticeId) {
        return selectList(MesWmSalesNoticeLineDO::getNoticeId, noticeId);
    }

    default void deleteByNoticeId(Long noticeId) {
        delete(MesWmSalesNoticeLineDO::getNoticeId, noticeId);
    }

}
